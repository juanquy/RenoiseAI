-- push1_scale.lua
-- Isomorphic keyboard mode for Push 1.

local C    = require("push1_constants")
local Midi = require("push1_midi")

local M = {}

M.root_midi    = 0    -- C
M.scale_idx    = 1    -- Major
M.base_octave  = 3
M.step_advance = 1

local SCALES = {
  {name = "Major",      intervals = {0,2,4,5,7,9,11}},
  {name = "Minor",      intervals = {0,2,3,5,7,8,10}},
  {name = "Dorian",     intervals = {0,2,3,5,7,8,10}},
  {name = "Phrygian",   intervals = {0,1,3,5,7,8,10}},
  {name = "Lydian",     intervals = {0,2,4,6,7,9,11}},
  {name = "Mixolydian", intervals = {0,2,4,5,7,9,10}},
  {name = "Locrian",    intervals = {0,1,3,5,7,8,10}},
  {name = "Pentatonic", intervals = {0,2,4,7,9}},
  {name = "Blues",      intervals = {0,3,5,6,7,10}},
  {name = "Whole Ton",  intervals = {0,2,4,6,8,10}}
}

local NOTES = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}

function M.get_note_info(midi_val)
  local oct = math.floor(midi_val / 12) - 1
  local note = midi_val % 12
  local rel  = (midi_val - M.root_midi) % 12
  local scale = SCALES[M.scale_idx]
  local in_scale = false
  local is_root = (rel == 0)
  for _, interval in ipairs(scale.intervals) do
    if rel == interval then in_scale = true; break end
  end
  return is_root, in_scale, NOTES[note+1] .. oct
end

function M.render()
  if not Midi.is_connected() then return end
  for row = 0, 7 do
    for col = 0, 7 do
      -- Isomorphic layout: +5 semitones per row (4ths), +1 per column
      local midi_val = (M.base_octave + 1) * 12 + M.root_midi + (row * 5) + col
      local is_root, in_scale = M.get_note_info(midi_val)
      local color = C.LED.OFF
      if is_root then color = C.LED.SCALE_ROOT
      elseif in_scale then color = C.LED.SCALE_NOTE
      else color = C.LED.SCALE_NON end
      Midi.set_grid_led(row, col, color)
    end
  end
end

function M.handle_pad_press(row, col)
  local midi_val = (M.base_octave + 1) * 12 + M.root_midi + (row * 5) + col
  local song = renoise.song()
  
  -- Send MIDI to Renoise
  renoise.song().instruments[song.selected_instrument_index]:play_note_now(midi_val, 100, 1)

  -- If recording, insert into pattern
  if song.transport.edit_mode then
    local ep = song.transport.edit_pos
    local pi = song.sequencer.pattern_sequence[ep.sequence]
    local nc = song.patterns[pi]:track(song.selected_track_index):line(ep.line).note_columns[1]
    nc.note_value = midi_val
    nc.instrument_value = song.selected_instrument_index - 1
    
    -- Advance cursor
    local next_ln = ep.line + M.step_advance
    if next_ln <= song.patterns[pi].number_of_lines then
      song.transport.edit_pos = {sequence = ep.sequence, line = next_ln}
    end
  end
  Midi.set_grid_led(row, col, C.LED.GREEN_FULL)
end

function M.handle_pad_release(row, col)
  M.render() -- Restore colour
end

function M.handle_encoder(index, delta)
  if index == 1 then
    M.root_midi = (M.root_midi + delta) % 12
    M.render()
    return "Root: " .. NOTES[M.root_midi+1]
  elseif index == 2 then
    M.scale_idx = math.max(1, math.min(#SCALES, M.scale_idx + delta))
    M.render()
    return "Scale: " .. SCALES[M.scale_idx].name
  elseif index == 3 then
    M.base_octave = math.max(0, math.min(8, M.base_octave + delta))
    M.render()
    return "Octave: " .. M.base_octave
  end
end

function M.display_lines()
  local root_name = NOTES[M.root_midi+1]
  local scale_name = SCALES[M.scale_idx].name
  return {
    "  [ SCALE MODE ]  Isomorphic Keyboard (4ths layout)",
    string.format("  Root: %-10s  Scale: %-15s", root_name, scale_name),
    string.format("  Octave: %d        Advance: %d lines", M.base_octave, M.step_advance),
    "  Enc 1:Root  Enc 2:Scale  Enc 3:Octave  Enc 4:Advance"
  }
end

return M
