-- push1_matrix.lua
-- Pattern Matrix / Session View mode for Push 1.
-- Maps the 8x8 grid to the Renoise Pattern Matrix for live performance.

local C    = require("push1_constants")
local Midi = require("push1_midi")

local M = {}

M.track_offset = 0
M.seq_offset   = 0
M.dirty        = true -- Force initial render
local pressed_pads = {} -- row..","..col -> boolean
local last_seq = -1
local last_tracks = -1
local last_seq_off = -1
local last_track_off = -1

function M.render(force)
  if not Midi.is_connected() then return end
  local song = renoise.song()
  local num_tracks = song.sequencer_track_count
  local num_seq    = #song.sequencer.pattern_sequence
  local curr_seq   = song.transport.playback_pos.sequence

  -- Smart Throttling: Skip if nothing changed
  if not force and not M.dirty 
     and curr_seq == last_seq 
     and num_tracks == last_tracks 
     and M.seq_offset == last_seq_off 
     and M.track_offset == last_track_off then 
    return 
  end
  
  -- Mark state for this render attempt
  last_seq = curr_seq
  last_tracks = num_tracks
  last_seq_off = M.seq_offset
  last_track_off = M.track_offset

  -- 3. Main Render Loop
  renoise.app():show_status(string.format("Matrix View: %d Scenes, %d Tracks [Off: %d,%d]", num_seq, num_tracks, M.seq_offset, M.track_offset))

  for row = 0, 7 do
    local seq_idx = M.seq_offset + row + 1
    for col = 0, 7 do
      local trk_idx = M.track_offset + col + 1
      local color = C.LED.WHITE -- Base Stage
      
      -- SAFE LOOKUP: Use pcall for song structure to avoid crashes on blank patterns
      local ok, result = pcall(function()
        if seq_idx <= num_seq and trk_idx <= num_tracks then
          local pat_idx = song.sequencer.pattern_sequence[seq_idx]
          if pat_idx and pat_idx > 0 then
            local pat = song:pattern(pat_idx)
            if pat and trk_idx <= #pat.tracks then
                local track_data = pat:track(trk_idx)
                local has_data = not track_data.is_empty
                local is_muted = song.sequencer:pattern_track_is_muted(seq_idx, trk_idx)
                local is_playing = (seq_idx == curr_seq)
                
                if has_data then
                  if is_muted then return C.LED.RED_DIM
                  elseif is_playing then return C.LED.GREEN_FULL
                  else return C.LED.GREEN_DIM end
                else
                  return C.LED.AMBER_DIM
                end
            end
          end
          return C.LED.AMBER_DIM
        end
        return C.LED.WHITE -- Off-limits area
      end)
      
      if ok then color = result else color = C.LED.AMBER_DIM end

      -- Flash Feedback: Override with full brightness if pressed
      if pressed_pads[row .. "," .. col] then
        color = C.LED.AMBER_FULL
      end
      
      Midi.set_grid_led(row, col, color)
    end
    
    -- Scene Buttons (Right side)
    local scene_idx = M.seq_offset + row + 1
    local is_scene_playing = (scene_idx == curr_seq)
    Midi.set_button_led(C.BTN.SCENE[row+1], is_scene_playing and C.LED.GREEN_FULL or C.LED.AMBER_DIM)
  end
  M.dirty = false -- Final mark as clean after successful full render
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
  
  M.render(true)
end

function M.handle_pad_release(row, col)
  pressed_pads[row .. "," .. col] = nil
  M.render(true)
end

function M.handle_scene_press(index)
  -- Trigger entire row (Scene)
  local seq_idx = M.seq_offset + index
  if seq_idx <= #renoise.song().sequencer.pattern_sequence then
    renoise.song().transport.playback_pos = renoise.SongPos(seq_idx, 1)
  end
  M.render(true)
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
  M.render(true)
end

function M.scroll_tracks(delta)
  local num_tracks = renoise.song().sequencer_track_count
  M.track_offset = math.max(0, math.min(num_tracks - 1, M.track_offset + delta))
  M.render(true)
end

function M.page_scroll(delta)
    local num_seq = #renoise.song().sequencer.pattern_sequence
    M.seq_offset = math.max(0, math.min(num_seq - 1, M.seq_offset + (delta * 8)))
    M.render(true)
end

function M.display_lines()
  local song = renoise.song()
  return {
    "  [ MATRIX MODE ]  Live Mode (Amber Stage)",
    string.format("  Seq: %d-%d (Scenes)  Tracks: %d-%d", 
      M.seq_offset + 1, math.min(#song.sequencer.pattern_sequence, M.seq_offset + 8),
      M.track_offset + 1, math.min(song.sequencer_track_count, M.track_offset + 8)),
    "  Encoders: Volume Mixer  |  Scene Buttons: Launch Row",
    "  Tactical: [REPEAT] Loop, [ACCENT] Click, [USER] Tap Tempo"
  }
end

return M
