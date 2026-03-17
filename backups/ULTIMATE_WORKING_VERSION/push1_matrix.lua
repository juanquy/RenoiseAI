-- push1_matrix.lua
-- Pattern Matrix / Session View mode for Push 1.
-- Maps the 8x8 grid to the Renoise Pattern Matrix for live performance.

local C    = require("push1_constants")
local Midi = require("push1_midi")

local M = {}

M.track_offset = 0
M.seq_offset   = 0

function M.render()
  if not Midi.is_connected() then return end
  local song = renoise.song()
  local num_tracks = song.sequencer_track_count
  local num_seq    = #song.sequencer.pattern_sequence
  local curr_seq   = song.transport.playback_pos.sequence

  for row = 0, 7 do
    local seq_idx = M.seq_offset + row + 1
    if seq_idx > num_seq then
      for col = 0, 7 do Midi.set_grid_led(row, col, 0) end
    else
      for col = 0, 7 do
        local trk_idx = M.track_offset + col + 1
        local color = 0
        
        if trk_idx <= num_tracks then
          local has_data = not song:pattern(song.sequencer.pattern_sequence[seq_idx]):track(trk_idx).is_empty
          local is_muted = song.sequencer:pattern_track_is_muted(seq_idx, trk_idx)
          local is_playing = (seq_idx == curr_seq)
          
          if not has_data then
            color = 0 -- Off
          elseif is_muted then
            color = C.LED.AMBER_DIM -- Muted slot
          elseif is_playing then
            color = C.LED.GREEN_FULL -- Currently playing slot
          else
            color = C.LED.GREEN_DIM -- Active but not playing
          end
        end
        
        Midi.set_grid_led(row, col, color)
      end
    end
  end
end

function M.handle_pad_press(row, col)
  local song = renoise.song()
  local seq_idx = M.seq_offset + row + 1
  local trk_idx = M.track_offset + col + 1
  
  if seq_idx > #song.sequencer.pattern_sequence then return end
  if trk_idx > song.sequencer_track_count then return end

  -- Toggle pattern-track mute
  local was_muted = song.sequencer:pattern_track_is_muted(seq_idx, trk_idx)
  song.sequencer:set_pattern_track_is_muted(seq_idx, trk_idx, not was_muted)
  
  M.render()
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

function M.display_lines()
  local song = renoise.song()
  return {
    "  [ MATRIX MODE ]  Renoise Pattern Matrix (Session)",
    string.format("  Sequence: %d - %d  Tracks: %d - %d", 
      M.seq_offset + 1, math.min(#song.sequencer.pattern_sequence, M.seq_offset + 8),
      M.track_offset + 1, math.min(song.sequencer_track_count, M.track_offset + 8)),
    "  Press pads to Mute/Unmute pattern loops.",
    "  Arrows to scroll matrix. [SESSION] returns to Tracker."
  }
end

return M
