-- push1_step.lua
-- Step sequencer mode for Push 1.

local C    = require("push1_constants")
local Midi = require("push1_midi")

local M = {}

M.track_offset = 0
M.step_offset  = 0 -- in lines
M.steps_per_page = 8

function M.render(playhead_line)
  if not Midi.is_connected() then return end
  local song = renoise.song()
  local seq  = song.selected_sequence_index
  local pi   = song.sequencer.pattern_sequence[seq]
  local pat  = song.patterns[pi]

  for row = 0, 7 do
    local trk_idx = M.track_offset + (7 - row) + 1
    if trk_idx > song.sequencer_track_count then
      for col = 0, 7 do Midi.set_grid_led(row, col, 0) end
    else
      local track = song:track(trk_idx)
      for col = 0, 7 do
        local line_idx = M.step_offset + col + 1
        local color = 0
        
        if line_idx <= pat.number_of_lines then
          local nc = pat:track(trk_idx):line(line_idx).note_columns[1]
          if nc and nc.note_value < 120 then
            color = C.LED.GREEN_MED
          end
          
          -- Playhead
          if line_idx == playhead_line then
            color = (color > 0) and C.LED.AMBER_FULL or C.LED.AMBER_MED
          elseif (line_idx - 1) % 4 == 0 then
             -- Beat markers
             if color == 0 then color = 1 end -- Amber dim tiny
          end
        end
        Midi.set_grid_led(row, col, color)
      end
    end
  end
end

function M.follow_playhead(line)
  local page = math.floor((line-1) / 8)
  M.step_offset = page * 8
  M.render(line)
end

function M.scroll_page(delta)
  M.step_offset = math.max(0, M.step_offset + delta * 8)
  M.render()
end

function M.scroll_tracks(delta)
  M.track_offset = math.max(0, M.track_offset + delta)
  M.render()
end

function M.handle_pad_press(row, col)
  local song = renoise.song()
  local trk_idx = M.track_offset + (7 - row) + 1
  local line_idx = M.step_offset + col + 1
  
  if trk_idx > song.sequencer_track_count then return end
  local pi = song.sequencer.pattern_sequence[song.selected_sequence_index]
  local pat = song.patterns[pi]
  if line_idx > pat.number_of_lines then return end

  local nc = pat:track(trk_idx):line(line_idx).note_columns[1]
  if nc.note_value < 120 then
    nc:clear()
  else
    nc.note_value = 48 -- C-4
    nc.instrument_value = song.selected_instrument_index - 1
  end
  M.render()
end

function M.display_lines()
  local song = renoise.song()
  local start_step = M.step_offset + 1
  local end_step = M.step_offset + 8
  return {
    "  [ STEP MODE ]  8 Tracks x 8 Steps",
    string.format("  Lines: %d - %d  (Scroll with Up/Down)", start_step, end_step),
    string.format("  Tracks: %d - %d (Scroll with Left/Right)", M.track_offset + 1, M.track_offset + 8),
    "  Enc 2:Page  Enc 3:Track  [DUPLICATE]=Rest  [DOUBLE]=Double"
  }
end

return M
