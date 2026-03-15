-- push1_grid.lua
-- Renders the Renoise Pattern Editor grid onto the Push 1 pads.

local C    = require("push1_constants")
local Midi = require("push1_midi")

local M = {}

M.row_offset   = 0
M.track_offset = 0

function M.render(playhead_line)
  if not Midi.is_connected() then return end
  local song = renoise.song()
  local seq  = song.selected_sequence_index
  local pi   = song.sequencer.pattern_sequence[seq]
  local pat  = song.patterns[pi]
  local sel_trk = song.selected_track_index
  local num_tracks = song.sequencer_track_count
  
  -- Pre-cache track objects for the current 8 visible columns
  local visible_tracks = {}
  for col = 0, 7 do
    local trk_idx = M.track_offset + col + 1
    if trk_idx <= num_tracks then
      visible_tracks[col] = {
        obj = song:track(trk_idx),
        idx = trk_idx,
        pat_track = pat:track(trk_idx)
      }
    end
  end

  for row = 0, 7 do
    local line_idx = M.row_offset + (7 - row) + 1
    if line_idx > pat.number_of_lines then
      for col = 0, 7 do Midi.set_grid_led(row, col, 0) end
    else
      for col = 0, 7 do
        local trk_data = visible_tracks[col]
        local color = 0
        
        if trk_data then
          local line = trk_data.pat_track:line(line_idx)
          local nc = line and line.note_columns[1]
          if nc and nc.note_value < 120 then
            local vel = nc.volume_value
            if vel == 255 then vel = 100 end -- Default
            if vel > 90 then color = C.LED.GREEN_FULL
            elseif vel > 45 then color = C.LED.GREEN_MED
            else color = C.LED.GREEN_DIM end
          elseif trk_data.idx == sel_trk then
            color = C.LED.AMBER_DIM -- Visual cursor
          end
        end

        -- Playhead highlight
        if playhead_line and line_idx == playhead_line then
          color = (color > 0) and C.LED.AMBER_FULL or C.LED.AMBER_MED
        end

        Midi.set_grid_led(row, col, color)
      end
    end
  end
end

function M.follow_playhead(line)
  -- Center view on playhead if it goes off-screen
  if line < M.row_offset + 1 or line > M.row_offset + 8 then
    M.row_offset = math.max(0, line - 4)
  end
  M.render(line)
end

function M.scroll_rows(delta)
  local max_lines = renoise.song().patterns[renoise.song().sequencer.pattern_sequence[renoise.song().selected_sequence_index]].number_of_lines
  M.row_offset = math.max(0, math.min(max_lines - 8, M.row_offset + delta))
  M.render()
end

function M.scroll_tracks(delta)
  M.track_offset = math.max(0, math.min(renoise.song().sequencer_track_count - 1, M.track_offset + delta))
  M.render()
end

function M.handle_pad_press(row, col, velocity)
  local song     = renoise.song()
  local line_idx = M.row_offset + (7 - row) + 1
  local trk_idx  = M.track_offset + col + 1
  
  if trk_idx > song.sequencer_track_count then return end
  
  local seq = song.selected_sequence_index
  local pi  = song.sequencer.pattern_sequence[seq]
  local pat = song.patterns[pi]
  if line_idx > pat.number_of_lines then return end

  local nc = pat:track(trk_idx):line(line_idx).note_columns[1]
  if nc.note_value < 120 then
    nc:clear()
  else
    nc.note_value = 48 -- C-4
    nc.instrument_value = song.selected_instrument_index - 1
    nc.volume_value = velocity
  end
  M.render()
end

return M
