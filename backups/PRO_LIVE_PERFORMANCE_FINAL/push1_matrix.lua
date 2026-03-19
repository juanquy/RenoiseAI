-- push1_matrix.lua
-- Pattern Matrix / Session View mode for Push 1.
-- Maps the 8x8 grid to the Renoise Pattern Matrix for live performance.

local C    = require("push1_constants")
local Midi = require("push1_midi")

local M = {}

M.track_offset = 0
M.seq_offset   = 0
local pressed_pads = {} -- row..","..col -> boolean

function M.render()
  if not Midi.is_connected() then return end
  local song = renoise.song()
  local num_tracks = song.sequencer_track_count
  local num_seq    = #song.sequencer.pattern_sequence
  local curr_seq   = song.transport.playback_pos.sequence

  for row = 0, 7 do
    local seq_idx = M.seq_offset + row + 1
    if seq_idx > num_seq then
      -- Stage: Use White to signal Live Mode
      for col = 0, 7 do Midi.set_grid_led(row, col, C.LED.WHITE) end
    else
      for col = 0, 7 do
        local trk_idx = M.track_offset + col + 1
        local color = C.LED.WHITE -- Background Stage (White)
        
        if trk_idx <= num_tracks then
          local has_data = not song:pattern(song.sequencer.pattern_sequence[seq_idx]):track(trk_idx).is_empty
          local is_muted = song.sequencer:pattern_track_is_muted(seq_idx, trk_idx)
          local is_playing = (seq_idx == curr_seq)
          
          if has_data then
            if is_muted then
              color = C.LED.RED_DIM -- Muted slot
            elseif is_playing then
              color = C.LED.GREEN_FULL -- Currently playing slot
            else
              color = C.LED.GREEN_DIM -- Active but not playing
            end
          else
             color = C.LED.AMBER_DIM -- Empty slot with data-capable track
          end
        end

        -- Flash Feedback: Override with full brightness if pressed
        if pressed_pads[row .. "," .. col] then
          color = C.LED.AMBER_FULL
        end
        
        Midi.set_grid_led(row, col, color)
      end
    end
    
    -- Scene Buttons (Right side)
    local scene_idx = M.seq_offset + row + 1
    local is_scene_playing = (scene_idx == curr_seq)
    Midi.set_button_led(C.BTN.SCENE[row+1], is_scene_playing and C.LED.GREEN_FULL or C.LED.AMBER_DIM)
  end
end

function M.handle_pad_press(row, col)
  pressed_pads[row .. "," .. col] = true
  
  local song = renoise.song()
  local seq_idx = M.seq_offset + row + 1
  local trk_idx = M.track_offset + col + 1
  
  if seq_idx <= #song.sequencer.pattern_sequence and trk_idx <= song.sequencer_track_count then
    -- Toggle pattern-track mute
    local was_muted = song.sequencer:pattern_track_is_muted(seq_idx, trk_idx)
    song.sequencer:set_pattern_track_is_muted(seq_idx, trk_idx, not was_muted)
  end
  
  M.render()
end

function M.handle_pad_release(row, col)
  pressed_pads[row .. "," .. col] = nil
  M.render()
end

function M.handle_scene_press(index)
  -- Trigger entire row (Scene)
  local seq_idx = M.seq_offset + index
  if seq_idx <= #renoise.song().sequencer.pattern_sequence then
    renoise.song().transport.playback_pos = renoise.SongPos(seq_idx, 1)
  end
  M.render()
end

function M.handle_encoder(index, delta)
  -- Encoders 1-8 control Track Volumes in Matrix Mode
  local song = renoise.song()
  local trk_idx = M.track_offset + index
  if trk_idx <= song.sequencer_track_count then
    local track = song:track(trk_idx)
    local val = track.prepost_mixer.volume.value
    track.prepost_mixer.volume.value = math.max(0, math.min(math.sqrt(4), val + (delta * 0.05)))
  end
end

function M.scroll_seq(delta)
  local num_seq = #renoise.song().sequencer.pattern_sequence
  M.seq_offset = math.max(0, math.min(num_seq - 1, M.seq_offset + delta))
  M.render()
end

function M.scroll_tracks(delta)
  local num_tracks = renoise.song().sequencer_track_count
  M.track_offset = math.max(0, math.min(num_tracks - 1, M.track_offset + delta))
  M.render()
end

function M.page_scroll(delta)
    local num_seq = #renoise.song().sequencer.pattern_sequence
    M.seq_offset = math.max(0, math.min(num_seq - 1, M.seq_offset + (delta * 8)))
    M.render()
end

function M.display_lines()
  local song = renoise.song()
  return {
    "  [ MATRIX MODE ]  Live Mode (White Stage)",
    string.format("  Seq: %d-%d (Scenes)  Tracks: %d-%d", 
      M.seq_offset + 1, math.min(#song.sequencer.pattern_sequence, M.seq_offset + 8),
      M.track_offset + 1, math.min(song.sequencer_track_count, M.track_offset + 8)),
    "  Encoders: Volume Mixer  |  Scene Buttons: Launch Row",
    "  Tactical: [REPEAT] Loop, [ACCENT] Click, [USER] Tap Tempo"
  }
end

return M
