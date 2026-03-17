-- main.lua
-- Push 1 for Renoise — v0.3.0
-- Integration for Ableton Push 1 as a native Renoise controller.

local C        = require("push1_constants")
local Midi     = require("push1_midi")
local Grid     = require("push1_grid")
local Scale    = require("push1_scale")
local Step     = require("push1_step")
local Matrix   = require("push1_matrix")
local Settings = require("push1_settings")

-- ──────────────────────────────────────────────
-- State
-- ──────────────────────────────────────────────
local shift_held      = false
local follow_mode     = true
local playback_obs    = nil
local last_line       = -1
local last_beat       = -1
local ai_composing    = false
local mute_mode       = false
local pending_vel     = 100
local master_idx_cache = -1

-- Mode cycles: tracker → scale → step → matrix
local mode = "tracker"

-- Debug Logger
local function log_push_error(msg)
  local log_path = "/tmp/push_debug.log"
  local f = io.open(log_path, "a")
  if f then
    f:write(os.date("%H:%M:%S") .. " | " .. msg .. "\n")
    f:close()
  end
end

-- Song observables (re-attached on new/loaded song)
local song_obs = {}

-- Pattern length snap values
local PAT_LENGTHS = {16, 24, 32, 48, 64, 96, 128, 192, 256}

-- Hot-reconnect
local reconnect_timer_id = nil
local RECONNECT_INTERVAL = 3.0
local is_connecting = false

-- State
local action_queue      = {}  -- Processed by GUI thread
local action_queue_lock = false

-- Thread-safe push to queue (MIDI thread)
local function enqueue_action(a)
  -- Simple lock-free boundary: we only append, GUI thread will pop
  action_queue[#action_queue + 1] = a
end

-- ──────────────────────────────────────────────
-- Utility
-- ──────────────────────────────────────────────

local function find_master_track()
  local song = renoise.song()
  if master_idx_cache > 0 and master_idx_cache <= #song.tracks then
    local t = song:track(master_idx_cache)
    if t.type == renoise.Track.TRACK_TYPE_MASTER then return t end
  end
  for i = 1, #song.tracks do
    if song:track(i).type == renoise.Track.TRACK_TYPE_MASTER then
      master_idx_cache = i
      return song:track(i)
    end
  end
  return song:track(song.sequencer_track_count + 1) -- Fallback
end

local function progress_bar(ratio, width)
  local filled = math.max(0, math.min(width, math.floor(ratio * width + 0.5)))
  return string.rep("#", filled) .. string.rep("-", width - filled)
end

local function elapsed_time()
  -- Optimized time calculation: only re-calculates if sequence/line changed
  -- and uses a basic estimative or cached values if needed.
  local song = renoise.song()
  local pos = song.transport.playback_pos
  local bpm = song.transport.bpm
  local lpb = song.transport.lpb
  
  -- Simple approximate seconds calculation for performance
  local total_beats = ((pos.sequence - 1) * 4) + ((pos.line - 1) / lpb)
  local secs = total_beats * (60 / bpm)
  
  return string.format("%02d:%02d", math.floor(secs/60), math.floor(secs)%60)
end

-- ──────────────────────────────────────────────
-- Display
-- ──────────────────────────────────────────────

local function update_button_leds()
  if not Midi.is_connected() then return end
  local song = renoise.song()
  if not song then return end
  local t = song.transport

  -- Transport LEDs
  Midi.set_button_led(C.BTN.PLAY, t.playing and C.LED.GREEN_FULL or C.LED.GREEN_DIM)
  Midi.set_button_led(C.BTN.RECORD, t.edit_mode and C.LED.RED_FULL or C.LED.RED_DIM)
  
  -- View Indicators (Renoise UI State)
  local window = renoise.app().window
  local active_up = window.active_upper_frame
  local active_down = window.active_lower_frame
  
  Midi.set_button_led(C.BTN.SESSION, (mode == "matrix") and 4 or 1)
  Midi.set_button_led(C.BTN.NOTE, (mode == "tracker" or mode == "scale") and 4 or 1)
  Midi.set_button_led(C.BTN.TRACK, active_up == renoise.ApplicationWindow.UPPER_FRAME_MIXER and 4 or 1)
  
  Midi.set_button_led(C.BTN.DEVICE, (window.lower_frame_is_visible and (active_down == renoise.ApplicationWindow.LOWER_FRAME_INSTRUMENT_SAMPLE_EDITOR or active_down == 3)) and 4 or 1)
  Midi.set_button_led(C.BTN.CLIP, (window.lower_frame_is_visible and (active_down == renoise.ApplicationWindow.LOWER_FRAME_INSTRUMENT_PLUGINS or active_down == 4)) and 4 or 1)
  Midi.set_button_led(C.BTN.BROWSE, (window.lower_frame_is_visible and (active_down == renoise.ApplicationWindow.LOWER_FRAME_INSTRUMENT_MIDI or active_down == 5)) and 4 or 1)

  -- Top Selection Buttons (1-5) Highlights
  Midi.set_button_led(C.SELECT_BTNS[1], active_up == renoise.ApplicationWindow.UPPER_FRAME_PATTERN_EDITOR and 4 or 1)
  Midi.set_button_led(C.SELECT_BTNS[2], active_up == renoise.ApplicationWindow.UPPER_FRAME_MIXER and 4 or 1)
  Midi.set_button_led(C.SELECT_BTNS[3], (window.lower_frame_is_visible and (active_down == renoise.ApplicationWindow.LOWER_FRAME_INSTRUMENT_SAMPLE_EDITOR or active_down == 3)) and 4 or 1)
  Midi.set_button_led(C.SELECT_BTNS[4], (window.lower_frame_is_visible and (active_down == renoise.ApplicationWindow.LOWER_FRAME_INSTRUMENT_PLUGINS or active_down == 4)) and 4 or 1)
  Midi.set_button_led(C.SELECT_BTNS[5], (window.lower_frame_is_visible and (active_down == renoise.ApplicationWindow.LOWER_FRAME_INSTRUMENT_MIDI or active_down == 5)) and 4 or 1)
  
  -- Remaining select buttons off/dim
  Midi.set_button_led(C.SELECT_BTNS[6], 1)
  Midi.set_button_led(C.SELECT_BTNS[7], 1)
  Midi.set_button_led(C.SELECT_BTNS[8], 1)

  -- All Functional Buttons: Force value 1 (Dim) so labels are readable
  Midi.set_button_led(C.BTN.SHIFT, shift_held and 4 or 1)
  Midi.set_button_led(C.BTN.UNDO, 1)
  Midi.set_button_led(C.BTN.DELETE, 1)
  Midi.set_button_led(C.BTN.DUPLICATE, 1)
  Midi.set_button_led(C.BTN.UP, 1)
  Midi.set_button_led(C.BTN.DOWN, 1)
  Midi.set_button_led(C.BTN.LEFT, 1)
  Midi.set_button_led(C.BTN.RIGHT, 1)
  Midi.set_button_led(C.BTN.MUTE, 1)
  Midi.set_button_led(C.BTN.SOLO, 1)
  
  Midi.set_button_led(C.BTN.OCTAVE_UP, 1)
  Midi.set_button_led(C.BTN.OCTAVE_DOWN, 1)
  Midi.set_button_led(C.BTN.PAGE_LEFT, 1)
  Midi.set_button_led(C.BTN.PAGE_RIGHT, 1)
  
  -- Metronome feedback
  pcall(function() Midi.set_button_led(C.BTN.METRONOME, t.metronome_enabled and 4 or 1) end)
end

-- Notifications
local function show_mode_notification(msg)
  local full_msg = "🎹 PUSH 1 >> " .. msg
  renoise.app():show_status(full_msg)
  print(full_msg)
end

local last_display_lines = {"", "", "", ""}

-- Refresh the LCD display based on current mode
local function update_display()
  pcall(function()
    if not Midi.is_connected() then return end

    local lines = {}
    if mode == "scale" then
      lines = Scale.display_lines()
    elseif mode == "step" then
      lines = Step.display_lines()
    elseif mode == "matrix" then
      lines = Matrix.display_lines()
    elseif ai_composing then
      lines = { "  AI SUITE — Composing...", "  Please wait", "  (request sent to local server)", "  Press [NEW] again to cancel" }
    else
      local song = renoise.song()
      local t    = song.transport
      if not t then return end

      -- Line 1: Encoder Labels (Aligned with the 8 knobs)
      -- Each slot is approx 8.5 chars. Let's use 8 chars + 1 space.
      lines[1] = " BPM      LINE      TRACK     VOL       --        LPB       --        INST"

      -- Line 2: Values & Song Position
      local bpm_str = string.format("%.1f", t.bpm)
      local seq_idx = song.selected_sequence_index
      local trk_idx = song.selected_track_index
      local vol_pct = math.floor(find_master_track().prefx_volume.value / 3.0 * 100)
      local inst_idx = song.selected_instrument_index
      
      lines[2] = string.format(" %-8s %-9d %-9d %-9d           %-10d          %-4d", 
                  bpm_str, song.selected_line_index, trk_idx, vol_pct, t.lpb, inst_idx)

      -- Line 3: Pattern Info & Name
      local pat_name = ""
      pcall(function()
        local pi = song.sequencer.pattern_sequence[seq_idx]
        pat_name = song.patterns[pi].name or ""
      end)
      lines[3] = string.format(" Seq: %02d  Pattern: %-48s", seq_idx, pat_name:sub(1,40))

      -- Line 4: Transport Status & Progress Bar
      local status = t.playing and "PLAY >>" or "STOP ||"
      local bar_ratio = 0
      pcall(function()
        local pi = song.sequencer.pattern_sequence[seq_idx]
        local pl = song.patterns[pi].number_of_lines
        bar_ratio = (t.playback_pos.line - 1) / math.max(1, pl - 1)
      end)
      local bar = progress_bar(math.min(1, bar_ratio), 30)
      lines[4] = string.format(" %-8s [%s] %s  %s", status, bar, elapsed_time(), follow_mode and "FOLLOW" or "")
    end

    -- Send all lines to Midi (it handles hardware diff-ing)
    for i = 1, 4 do
      Midi.write_display(i, lines[i])
    end
    
    update_button_leds()
  end)
end

-- ──────────────────────────────────────────────
-- Handlers
-- ──────────────────────────────────────────────

local function handle_transport(id, vel)
  if vel == 0 then return end
  local song = renoise.song()
  if not song then return end
  local t = song.transport
  
  -- EXPANDED RANGE: Support standard (85/86) and alternates (115/116, etc)
  local is_play = (id == C.BTN.PLAY or id == 85 or id == 20 or id == 12 or id == 105)
  local is_rec  = (id == C.BTN.RECORD or id == 86 or id == 21 or id == 13 or id == 106)

  if is_play then
    if t.playing then t:stop() else t:start(renoise.Transport.PLAYMODE_CONTINUE_PATTERN) end
  elseif is_rec then 
    t.edit_mode = not t.edit_mode
  elseif id == C.BTN.TAP_TEMPO or id == 3 or id == 58 then 
    t:tap_tempo() 
  end
  update_display()
end

local function handle_duplicate(vel)
  if vel == 0 then return end
  local song = renoise.song()
  if mode ~= "tracker" then
    pcall(function()
      local ep = song.transport.edit_pos
      local pi = song.sequencer.pattern_sequence[ep.sequence]
      local nc = song.patterns[pi]:track(song.selected_track_index):line(ep.line).note_columns[1]
      nc.note_value = 120 -- Off
      local step = (mode == "scale") and Scale.step_advance or 1
      song.transport.edit_pos = {sequence = ep.sequence, line = ep.line + step}
    end)
  else
    renoise.app():invoke_action("Sequencer:Duplicate Sequence")
  end
  update_display()
end

local function handle_double(vel)
  if vel == 0 then return end
  pcall(function()
    local song = renoise.song()
    local seq = song.selected_sequence_index
    local pat_idx = song.sequencer.pattern_sequence[seq]
    local pat = song.patterns[pat_idx]
    pat.number_of_lines = math.min(512, pat.number_of_lines * 2)
  end)
  update_display()
end

local function handle_navigation(id, val)
  if val == 0 then return end
  local song = renoise.song()
  
  if id == C.BTN.UP then
    if mode == "matrix" then 
      Matrix.scroll_seq(-1)
      song.selected_sequence_index = math.max(1, song.selected_sequence_index - 1)
    elseif shift_held then 
      song.selected_sequence_index = math.max(1, song.selected_sequence_index - 1)
    else 
      song.selected_line_index = math.max(1, song.selected_line_index - 1)
    end
  elseif id == C.BTN.DOWN then
    if mode == "matrix" then 
      Matrix.scroll_seq(1)
      song.selected_sequence_index = math.min(#song.sequencer.pattern_sequence, song.selected_sequence_index + 1)
    elseif shift_held then
      song.selected_sequence_index = math.min(#song.sequencer.pattern_sequence, song.selected_sequence_index + 1)
    else 
      local max_lines = song.patterns[song.sequencer.pattern_sequence[song.selected_sequence_index]].number_of_lines
      song.selected_line_index = math.min(max_lines, song.selected_line_index + 1)
    end
  elseif id == C.BTN.LEFT then
    if mode == "matrix" then 
      Matrix.scroll_tracks(-1)
      song.selected_track_index = math.max(1, song.selected_track_index - 1)
    elseif shift_held then
      song.selected_track_index = math.max(1, song.selected_track_index - 8)
    else 
      song.selected_track_index = math.max(1, song.selected_track_index - 1)
    end
  elseif id == C.BTN.RIGHT then
    if mode == "matrix" then 
      Matrix.scroll_tracks(1)
      song.selected_track_index = math.min(#song.tracks, song.selected_track_index + 1)
    elseif shift_held then
      song.selected_track_index = math.min(#song.tracks, song.selected_track_index + 8)
    else 
      song.selected_track_index = math.min(#song.tracks, song.selected_track_index + 1)
    end
  end
  update_display()
end

local function handle_octave(id, val)
  if mode == "matrix" then
    Matrix.page_scroll(id == C.BTN.OCTAVE_UP and 1 or -1)
  else
    local current = song.transport.octave
    if id == C.BTN.OCTAVE_UP then song.transport.octave = math.min(8, current + 1)
    else song.transport.octave = math.max(0, current - 1) end
  end
  update_display()
end

local function handle_encoder(index, delta)
  local song = renoise.song()
  local t = song.transport
  
  if mode == "matrix" then
    Matrix.handle_encoder(index, delta)
    update_display()
    return
  end

  if mode == "step" then
    if index == 2 then Step.scroll_page(delta); update_display(); return end
    if index == 3 then Step.scroll_tracks(delta); update_display(); return end
  end

  if mode == "scale" then
    local msg = Scale.handle_encoder(index, delta)
    if msg then renoise.app():show_status(msg); update_display(); return end
  end

  if index == 1 then
    t.bpm = math.max(60, math.min(999, t.bpm + delta * (shift_held and 1.0 or 0.1)))
  elseif index == 2 then Grid.scroll_rows(delta)
  elseif index == 3 then Grid.scroll_tracks(delta)
  elseif index == 4 then
    local mt = find_master_track()
    if mt then
      mt.prefx_volume.value = math.max(0, math.min(3.0, mt.prefx_volume.value + delta * 0.02))
    end
  elseif index == 6 then t.lpb = math.max(1, math.min(32, t.lpb + delta))
  elseif index == 8 then song.selected_instrument_index = math.max(1, math.min(#song.instruments, song.selected_instrument_index+delta))
  end
  update_display()
end

local function toggle_mode(vel)
  if vel == 0 then return end
  if mode == "tracker" then mode = "scale"; Scale.render()
  elseif mode == "scale" then mode = "step"; Step.render()
  elseif mode == "step" then mode = "matrix"; Matrix.render()
  else mode = "tracker"; Grid.render() end
  update_display()
end

local function on_midi_message(msg)
  if not msg then return end

  local btn_id = msg.note or msg.cc
  local val = msg.velocity or msg.value or 0
  local pressed = (val > 0)

  -- Shift is safe to handle directly (only changes a local flag)
  if btn_id == C.BTN.SHIFT then
    shift_held = pressed
    return
  end

  -- Status Bar Flash Sniffer (DISABLED TO PREVENT NOTIF OVERWRITE)
  -- if pressed and not msg.is_pad then
  --   local debug_msg = string.format("[AG-DEBUG] PUSH CC: %d (Value: %d)", btn_id or 0, val)
  --   renoise.app():show_status(debug_msg)
  --   print(debug_msg)
  -- end

  -- Queue everything else for safe GUI-thread processing
  enqueue_action({
    btn_id = btn_id, val = val, pressed = pressed,
    is_pad = msg.is_pad, pad_row = msg.pad_row, pad_col = msg.pad_col,
    is_encoder = msg.is_encoder, encoder_index = msg.encoder_index,
    encoder_delta = msg.encoder_delta, kind = msg.kind
  })
end

local function process_action(a)
  if a.btn_id == C.BTN.FIXED_LENGTH then toggle_mode(a.val); return end
  if a.btn_id == C.BTN.DUPLICATE then handle_duplicate(a.val); return end
  if a.btn_id == C.BTN.DOUBLE then handle_double(a.val); return end

  if a.is_pad then
    if mode == "scale" then
      if a.kind == "note_on" then Scale.handle_pad_press(a.pad_row, a.pad_col)
      else Scale.handle_pad_release(a.pad_row, a.pad_col) end
    elseif mode == "step" then if a.kind == "note_on" then Step.handle_pad_press(a.pad_row, a.pad_col) end
    else if a.kind == "note_on" then Grid.handle_pad_press(a.pad_row, a.pad_col, pending_vel) end end
    return
  end

  if a.is_encoder then handle_encoder(a.encoder_index, a.encoder_delta); return end

  if a.pressed and a.btn_id then
    -- CC Sniffer (High Visibility)
    if not a.is_pad then
        renoise.app():show_status(string.format("[Push 1] CC %d Press - Val %d", a.btn_id, a.val))
    end
  end

  -- 1. NUCLEAR PRIORITY: Mode Switching
  if a.pressed then
    if a.btn_id == C.BTN.SESSION or a.btn_id == 51 then
      -- FORCE RE-ENTER MATRIX MODE
      mode = "matrix"
      Matrix.dirty = true
      renoise.app():show_status(">> MATRIX (LIVE) MODE ACTIVE <<")
      pcall(function() 
        renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_PATTERN_EDITOR 
        Matrix.render(true)
      end)
      update_display()
      Midi.flush_hardware()
      return -- Exit early for mode switches
    elseif a.btn_id == C.BTN.NOTE or a.btn_id == 50 then
      if shift_held then
        mode = "scale"
        renoise.app():show_status(">> SCALE MODE ACTIVE <<")
      else
        mode = "tracker"
        renoise.app():show_status(">> TRACKER MODE ACTIVE <<")
      end
      pcall(function() 
        renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_PATTERN_EDITOR 
        if mode == "scale" then Scale.render() else Grid.render() end
      end)
      update_display()
      return -- Exit early
    end
  end

  -- Navigation & Focus
  if a.pressed then
    if a.btn_id == C.BTN.UP or a.btn_id == C.BTN.DOWN or a.btn_id == C.BTN.LEFT or a.btn_id == C.BTN.RIGHT then
      handle_navigation(a.btn_id, a.val)
    elseif a.btn_id == C.BTN.OCTAVE_UP or a.btn_id == C.BTN.OCTAVE_DOWN then
      handle_octave(a.btn_id, a.val)
    elseif a.btn_id == C.BTN.MUTE then
      local track = renoise.song().selected_track
      track.mute_state = (track.mute_state == renoise.Track.MUTE_STATE_ACTIVE) and renoise.Track.MUTE_STATE_MUTED or renoise.Track.MUTE_STATE_ACTIVE
    elseif a.btn_id == C.BTN.SOLO then
      renoise.song().selected_track:solo()
    elseif a.btn_id == C.BTN.UNDO then
      renoise.app():undo()
    elseif a.btn_id == C.BTN.DELETE then
      renoise.app():invoke_action("Edit:Delete")
    elseif a.btn_id == C.BTN.MASTER then
      local song = renoise.song()
      for i = 1, #song.tracks do
        if song:track(i).type == renoise.Track.TRACK_TYPE_MASTER then
          song.selected_track_index = i
          break
        end
      end
      update_display()
    elseif a.btn_id == C.BTN.METRONOME then
      local t = renoise.song().transport
      t.metronome_enabled = not t.metronome_enabled
      update_button_leds()
    elseif a.btn_id == C.BTN.SCALES or a.btn_id == 58 then
      -- Tactical Jump to Scale Mode
      show_mode_notification("SCALE (KEYBOARD) MODE [ON]")
      mode = "scale"
      renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_PATTERN_EDITOR
      Scale.render()
      update_display()
    elseif a.btn_id == C.BTN.REPEAT or a.btn_id == 56 then
      -- Tactical: Toggle Pattern Loop
      local t = renoise.song().transport
      t.loop_block_enabled = not t.loop_block_enabled
      show_mode_notification("LOOP BLOCK: " .. (t.loop_block_enabled and "ON" or "OFF"))
    elseif a.btn_id == C.BTN.ACCENT or a.btn_id == 57 then
      -- Tactical: Metronome
      local t = renoise.song().transport
      t.metronome_enabled = not t.metronome_enabled
      show_mode_notification("METRONOME: " .. (t.metronome_enabled and "ON" or "OFF"))
    elseif a.btn_id == C.BTN.USER or a.btn_id == 59 then
      -- Tactical: Tap Tempo
      renoise.song().transport:tap_tempo()
      show_mode_notification("TAP TEMPO TRIGGERED")
    elseif a.btn_id >= 36 and a.btn_id <= 43 then
      -- Scene Launch Buttons (Right side)
      for i, cc in ipairs(C.BTN.SCENE) do
        if a.btn_id == cc then
          if mode == "matrix" then Matrix.handle_scene_press(i) end
          break
        end
      end
    elseif a.btn_id == C.BTN.TRACK or a.btn_id == 112 then
      -- [Mix] Tab (Mixer)
      pcall(function() renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_MIXER end)
      update_display()
    elseif a.btn_id == C.BTN.DEVICE or a.btn_id == 110 then
      -- [Sampler] Tab
      pcall(function() renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_INSTRUMENT_SAMPLE_EDITOR end)
      update_display()
    elseif a.btn_id == C.BTN.CLIP or a.btn_id == 113 then
      -- [Plugin] Tab (ID 8)
      pcall(function() renoise.app().window.active_middle_frame = 8 end)
      update_display()
    elseif a.btn_id == C.BTN.BROWSE or a.btn_id == 111 then
      -- [MIDI] Tab (ID 9)
      pcall(function() renoise.app().window.active_middle_frame = 9 end)
      update_display()
    
    -- REDUNDANT MAPPING: Top Selection Buttons (1-5)
    elseif a.btn_id == C.SELECT_BTNS[1] then 
      pcall(function() renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_PATTERN_EDITOR end)
      mode = "tracker"
      update_display()
    elseif a.btn_id == C.SELECT_BTNS[2] then
      pcall(function() renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_MIXER end)
      update_display()
    elseif a.btn_id == C.SELECT_BTNS[3] then
      pcall(function() renoise.app().window.active_middle_frame = renoise.ApplicationWindow.MIDDLE_FRAME_INSTRUMENT_SAMPLE_EDITOR end)
      update_display()
    elseif a.btn_id == C.SELECT_BTNS[4] then
      pcall(function() renoise.app().window.active_middle_frame = 8 end)
      update_display()
    elseif a.btn_id == C.SELECT_BTNS[5] then
      pcall(function() renoise.app().window.active_middle_frame = 9 end)
      update_display()

    elseif a.btn_id == C.BTN.PLAY or a.btn_id == C.BTN.RECORD or a.btn_id == C.BTN.TAP_TEMPO then 
      handle_transport(a.btn_id, a.val)
    end
  end
end

-- ──────────────────────────────────────────────
-- Notifiers
-- ──────────────────────────────────────────────

local heartbeat_toggle = false
local function tool_tick()
  -- 1. Atomically swap and clear the queue to prevent race conditions
  local current_actions = action_queue
  action_queue = {}
  
  -- 2. Progress Input Actions on GUI thread
  -- 1. Priority: Process actions
  while #current_actions > 0 do
    local a = table.remove(current_actions, 1)
    local ok, err = pcall(function() process_action(a) end)
    if not ok then renoise.app():show_status("Action Process Err: " .. tostring(err)) end
  end
  
  -- 3. Track Playhead & Render
  -- 3. Render Loop
  local ok, err = pcall(function()
    if not Midi.is_connected() then return end
    local song = renoise.song()
    if not song then return end
    local pos = song.transport.playback_pos
    
    if mode == "tracker" or mode == "step" then
      if pos.line ~= last_line then
        last_line = pos.line
        if mode == "tracker" then Grid.render(pos.line)
        elseif mode == "step" then Step.render(pos.line) end
        
        local beat = math.floor((pos.line-1)/math.max(1, song.transport.lpb))
        if beat ~= last_beat then 
          last_beat = beat
          update_display() 
        end
      end
    elseif mode == "matrix" then
      -- Matrix rendering handles its own throttling via Matrix.dirty
      Matrix.render()
      
      -- Still update display on beat changes if playing
      if pos.line ~= last_line then
        last_line = pos.line
        local beat = math.floor((pos.line-1)/math.max(1, song.transport.lpb))
        if beat ~= last_beat then 
          last_beat = beat
          update_display() 
        end
      end
    else
      -- scale mode or others
      if pos.line ~= last_line then last_line = pos.line end
    end
  end)
  if not ok then renoise.app():show_status("Render Err: " .. tostring(err)) end

  -- 4. Flush Hardware State (Always run to clear buffers)
  Midi.flush_hardware()
  
  -- 5. Heartbeat (Visual confirmation in Renoise Status Bar)
  heartbeat_toggle = not heartbeat_toggle
  if heartbeat_toggle then
    -- Very lightweight: only shows if dev tools are on or manually requested
    -- but enough to prove we didn't freeze.
  end
end

local function attach_song_observables()
  for _, obs in ipairs(song_obs) do pcall(obs.remove) end
  song_obs = {}
  local song = renoise.song()
  
  -- Display redraw notifiers
  local redraw = function() update_display() end
  local grid_redraw = function() 
    if mode == "tracker" then Grid.render() 
    elseif mode == "step" then Step.render() 
    elseif mode == "matrix" then Matrix.render() end 
    update_display()
  end

  -- BPM/LPB changes
  song.transport.bpm_observable:add_notifier(redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.transport.bpm_observable:remove_notifier(redraw) end) end }
  song.transport.lpb_observable:add_notifier(redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.transport.lpb_observable:remove_notifier(redraw) end) end }
  song.transport.playing_observable:add_notifier(redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.transport.playing_observable:remove_notifier(redraw) end) end }
  song.transport.edit_mode_observable:add_notifier(redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.transport.edit_mode_observable:remove_notifier(redraw) end) end }

  -- Selection changes
  song.selected_track_index_observable:add_notifier(grid_redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.selected_track_index_observable:remove_notifier(grid_redraw) end) end }
  song.selected_instrument_index_observable:add_notifier(redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.selected_instrument_index_observable:remove_notifier(redraw) end) end }

  -- Master Volume change
  local master_track = find_master_track()
  if master_track then
    local master_vol_obs = master_track.prefx_volume.value_observable
    master_vol_obs:add_notifier(redraw)
    song_obs[#song_obs+1] = { remove = function() pcall(function() master_vol_obs:remove_notifier(redraw) end) end }
  end

  -- Tracks change (added/removed)
  song.tracks_observable:add_notifier(grid_redraw)
  song_obs[#song_obs+1] = { remove = function() pcall(function() song.tracks_observable:remove_notifier(grid_redraw) end) end }
end

-- Background reconnect disabled for stability

local monitor_log = {}
local function log_monitor(msg)
  table.insert(monitor_log, 1, msg)
  if #monitor_log > 10 then table.remove(monitor_log) end
end

local function connect(manual_in, manual_out)
  if is_connecting then return end
  is_connecting = true
  
  Midi.on_message_callback = on_midi_message
  local ok, status = Midi.connect(manual_in, manual_out)
  if ok then 
    attach_song_observables()
    update_display()
    if not renoise.tool():has_timer(tool_tick) then
      renoise.tool():add_timer(tool_tick, 110) -- Relaxed from 50ms for ALSA stability
    end
    renoise.app():show_status("Push 1: [PUSH-PRO-V16] Connected")
    -- API PROBE: Find all LOWER_FRAME constants
    local f = io.open("/tmp/push_debug.log", "w")
    if f then 
      f:write("--- API 6.2 V16 PROBE ---\n")
      -- Test various potential naming patterns
      local tests = {
        "LOWER_FRAME_SAMPLE_EDITOR", "LOWER_FRAME_INSTRUMENTS", 
        "LOWER_FRAME_INSTRUMENT_EDITOR", "LOWER_FRAME_PLUGINS",
        "LOWER_FRAME_MIDI", "LOWER_FRAME_INSTRUMENT_PROPERTIES"
      }
      for _, t in ipairs(tests) do
        local ok = pcall(function() return renoise.ApplicationWindow[t] end)
        f:write("AW_CONST (" .. t .. "): " .. (ok and "EXISTS" or "MISSING") .. "\n")
      end
      f:write("--- PROBE END ---\n")
      f:close() 
    end
  else
    renoise.app():show_status("Push 1: Connect failed: " .. tostring(status))
  end
  is_connecting = false
end

renoise.tool().app_new_document_observable:add_notifier(function()
  if Midi.is_connected() then attach_song_observables(); Grid.render(); update_display() end
end)

-- ──────────────────────────────────────────────
-- Cleanup & Auto-start
-- ──────────────────────────────────────────────
local function disconnect()
  -- 1. STOP TIMER FIRST (Prevents MIDI access during close)
  if renoise.tool():has_timer(tool_tick) then
    renoise.tool():remove_timer(tool_tick)
  end
  
  -- 2. Clean up song observers
  for _, obs in ipairs(song_obs) do pcall(obs.remove) end
  song_obs = {}
  
  -- 3. Close MIDI subsystem safely
  Midi.disconnect()
  renoise.app():show_status("Push 1: Disconnected.")
end

local diag_dialog = nil
local function show_all_ports_dialog()
  local in_devs = renoise.Midi.available_input_devices()
  local out_devs = renoise.Midi.available_output_devices()
  local vb = renoise.ViewBuilder()
  
  local log_col = vb:column { margin = 5, vb:text { text = "LIVE MIDI MONITOR:", font = "bold" } }
  local log_texts = {}
  for i=1,10 do
    log_texts[i] = vb:text { text = "-", font = "mono" }
    log_col:add_child(log_texts[i])
  end

  -- Update log timer
  renoise.tool():add_timer(function()
    if not diag_dialog or not diag_dialog.visible then return end
    local log = Midi.get_monitor_log()
    for i=1,10 do log_texts[i].text = log[i] or "-" end
  end, 100)
  
  local in_col = vb:column { margin = 5, vb:text { text = "CLICK TO CONNECT INPUT:", font = "bold" } }
  for i, n in ipairs(in_devs) do
    in_col:add_child(vb:button { 
      text = string.format("%d: %s", i, n),
      width = 300,
      notifier = function() connect(n, nil) end
    })
  end
  
  local out_col = vb:column { margin = 5, vb:text { text = "CLICK TO CONNECT OUTPUT:", font = "bold" } }
  for i, n in ipairs(out_devs) do
    out_col:add_child(vb:button { 
      text = string.format("%d: %s", i, n),
      width = 300,
      notifier = function() connect(nil, n) end
    })
  end

  local content = vb:column {
    margin = 15, spacing = 10,
    vb:text { text = "Push 1 Expert Monitor", font = "bold" },
    vb:text { text = "Press the PLAY button on hardware. If no code appears in monitor,", font = "italic" },
    vb:text { text = "click each INPUT button below one by one until it does.", font = "italic" },
    log_col,
    in_col,
    out_col,
    vb:button { 
      text = "Close", 
      width = 100,
      notifier = function() if diag_dialog then diag_dialog:close() end end 
    }
  }
  
  if diag_dialog and diag_dialog.visible then diag_dialog:show() 
  else diag_dialog = renoise.app():show_custom_dialog("Push 1 Expert", content) end
end

renoise.tool():add_menu_entry { name = "Main Menu:Tools:Push 1:Connect", invoke = function() connect() end }
renoise.tool():add_menu_entry { name = "Main Menu:Tools:Push 1:Disconnect", invoke = disconnect }
renoise.tool():add_menu_entry { name = "Main Menu:Tools:Push 1:Show All MIDI Ports", invoke = show_all_ports_dialog }
renoise.tool():add_menu_entry { name = "Main Menu:Tools:Push 1:Settings...", invoke = function() Settings.show_dialog(update_display) end }

-- LITERALLY NO BACKGROUND CODE. STABILITY FIRST.
