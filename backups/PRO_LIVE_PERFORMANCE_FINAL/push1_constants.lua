-- push1_constants.lua
-- Hardware constants and SysEx templates for Ableton Push 1.

local M = {}

-- ──────────────────────────────────────────────
-- Grid Layout (Pads)
-- ──────────────────────────────────────────────
M.GRID_ROWS = 8
M.GRID_COLS = 8

-- Pad MIDI notes: 36 (bottom-left) to 99 (top-right)
-- Row 0 is bottom, row 7 is top.
function M.pad_to_note(row, col)
  return 36 + (row * 8) + col
end

function M.note_to_pad(note)
  if note < 36 or note > 99 then return nil end
  local offset = note - 36
  local row = math.floor(offset / 8)
  local col = offset % 8
  return row, col
end

-- ──────────────────────────────────────────────
-- LCD Display (68 chars x 4 lines)
-- ──────────────────────────────────────────────
M.DISPLAY_WIDTH = 68

-- SysEx commands for each line
M.DISPLAY_LINE_CMDS = {0x18, 0x19, 0x1A, 0x1B}

function M.make_display_sysex(line, text)
  local line_cmd = M.DISPLAY_LINE_CMDS[line] or 0x18
  -- Pad text to 68 chars
  text = (text .. string.rep(" ", M.DISPLAY_WIDTH)):sub(1, M.DISPLAY_WIDTH)
  
  local msg = {0xF0, 0x47, 0x7F, 0x15, line_cmd, 0x00, 0x45, 0x00}
  for i = 1, #text do
    msg[#msg+1] = text:byte(i)
  end
  msg[#msg+1] = 0xF7
  return msg
end

-- Handshake strings
M.SYSEX_USER_MODE = {0xF0, 0x47, 0x7F, 0x15, 0x62, 0x00, 0x01, 0x01, 0xF7}
M.SYSEX_LIVE_MODE = {0xF0, 0x47, 0x7F, 0x15, 0x62, 0x00, 0x01, 0x00, 0xF7}

-- ──────────────────────────────────────────────
-- Buttons & Encoders (CC / Note values)
-- ──────────────────────────────────────────────
M.BTN = {
  -- Transport
  PLAY          = 85,
  RECORD        = 86,
  SHIFT         = 49,
  TAP_TEMPO     = 3,
  METRONOME     = 9,
  
  -- Navigation (D-Pad)
  UP            = 46,
  DOWN          = 47,
  LEFT          = 44,
  RIGHT         = 45,
  
  -- Focus / State
  MUTE          = 60,
  SOLO          = 61,
  SELECT        = 48,
  SESSION       = 51,
  NOTE          = 50,
  DEVICE        = 110,
  TRACK         = 112,
  BROWSE        = 111,
  CLIP          = 113,
  MASTER        = 28,
  
  -- Edit / Add
  UNDO          = 119,
  DELETE        = 118,
  DOUBLE        = 117,
  QUANTIZE      = 116,
  DUPLICATE     = 88,
  NEW           = 91,
  FIXED_LENGTH  = 90,
  ADD_EFFECT    = 52,
  ADD_TRACK     = 53,
  
  -- Note Section 
  OCTAVE_DOWN   = 54,
  OCTAVE_UP     = 55,
  REPEAT        = 56,
  ACCENT        = 57,
  SCALES        = 58,
  USER          = 59,
  PAGE_LEFT     = 62,
  PAGE_RIGHT    = 63,
  
  -- Grid
  SCENE         = {43, 42, 41, 40, 39, 38, 37, 36}, 
  
  -- Selection Buttons (Below LCD)
  SELECT_BTNS   = {102, 103, 104, 105, 106, 107, 108, 109},
  
  -- State Buttons (Above Pads)
  STATE_BTNS    = {20, 21, 22, 23, 24, 25, 26, 27},
}

M.ENCODER_CC = {71, 72, 73, 74, 75, 76, 77, 78, 79} -- 1-8 + Master

function M.encoder_delta(val)
  if val <= 64 then return val else return val - 128 end
end

-- ──────────────────────────────────────────────
-- LED Colours
-- ──────────────────────────────────────────────
M.LED = {
  OFF           = 0,
  AMBER_DIM     = 1,
  AMBER_MED     = 2,
  AMBER_FULL    = 3,
  AMBER_BLINK   = 4,
  RED_DIM       = 5,
  RED_MED       = 6,
  RED_FULL      = 7,
  YELLOW        = 8,
  GREEN_DIM     = 17,
  GREEN_MED     = 18,
  GREEN_FULL    = 19,
  GREEN_BLINK   = 20,
  -- Scale colours
  SCENE_ACTIVE  = 3, -- Amber
  SCENE_FILLED  = 17, -- Green dim
  SCALE_ROOT    = 19, -- Green
  SCALE_NOTE    = 17, -- Green dim
  SCALE_NON     = 1, -- Amber dim
  PLAYHEAD      = 3, -- Amber full
  WHITE         = 122, -- Cool White (Backlight)
}

return M
