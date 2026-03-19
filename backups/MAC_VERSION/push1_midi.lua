local C = require("push1_constants")
local bit = bit or require("bit")

local M = {}

M.midi_inputs = {} 
M.midi_outputs = {}
M.on_message_callback = nil
M.traffic_count = 0

-- Hardware State Buffers
local led_buffer      = {} -- Pads (Notes)
local led_state       = {} 
local btn_buffer      = {} -- Buttons (CCs)
local btn_state       = {}
local display_buffer  = {"", "", "", ""}
local display_state   = {nil, nil, nil, nil}

local monitor_log = {}
local function log_monitor(msg)
  table.insert(monitor_log, 1, msg)
  if #monitor_log > 15 then table.remove(monitor_log) end
end

function M.find_push_ports()
  local in_devs  = renoise.Midi.available_input_devices()
  local out_devs = renoise.Midi.available_output_devices()
  local in_p, out_p

  -- Mac-Specific Priority Match
  for _, n in ipairs(in_devs) do
    if n:find("Ableton Push") and n:find("User Port") then in_p = n; break end
  end
  for _, n in ipairs(out_devs) do
    if n:find("Ableton Push") and n:find("User Port") then out_p = n; break end
  end

  -- Fallback logic for Linux/Generic
  if not in_p then
    for _, n in ipairs(in_devs) do
      if n:lower():find("push") and (n:lower():find("user") or n:lower():find("port 2") or n:lower():find("midi 2")) and not n:lower():find("renoise") then in_p = n; break end
    end
  end
  if not out_p then
    for _, n in ipairs(out_devs) do
      if n:lower():find("push") and (n:lower():find("user") or n:lower():find("port 2") or n:lower():find("midi 2")) and not n:lower():find("renoise") then out_p = n; break end
    end
  end

  if not in_p then for _, n in ipairs(in_devs) do if n:lower():find("push") and not n:lower():find("renoise") then in_p = n; break end end end
  if not out_p then for _, n in ipairs(out_devs) do if n:lower():find("push") and not n:lower():find("renoise") then out_p = n; break end end end

  return in_p, out_p
end

function M.find_all_push_outputs()
  local out_devs = renoise.Midi.available_output_devices()
  
  -- Mac & Linux Fix: Prefer the User Port ONLY
  for _, n in ipairs(out_devs) do
    if n:find("Ableton Push") and n:find("User Port") then return {n} end
  end
  for _, n in ipairs(out_devs) do
    if n:lower():find("push") and (n:lower():find("user") or n:lower():find("port 2") or n:lower():find("midi 2")) and not n:lower():find("renoise") then return {n} end
  end
  
  -- Last resort: any Push output
  for _, n in ipairs(out_devs) do
    if n:lower():find("push") and not n:lower():find("renoise") then return {n} end
  end
  
  return {}
end

function M.connect(manual_in, manual_out)
  local auto_in, auto_out = M.find_push_ports()
  
  local in_targets = {}
  if manual_in then 
    in_targets = {manual_in} 
  else
    local auto_in, _ = M.find_push_ports()
    if auto_in then in_targets = {auto_in} end
  end

  local out_targets = (manual_out) and {manual_out} or M.find_all_push_outputs()
  if #in_targets == 0 or #out_targets == 0 then return false, "Push 1 hardware not found." end

  M.disconnect()

  local status_parts = {}
  for _, in_name in ipairs(in_targets) do
    local ok, _ = pcall(function()
      local dev = renoise.Midi.create_input_device(in_name, function(msg) M._on_raw_midi(msg, in_name) end)
      table.insert(M.midi_inputs, dev)
    end)
    if ok then table.insert(status_parts, in_name:match("([^ ]+)$") or in_name:sub(-10)) end
  end

  for _, out_name in ipairs(out_targets) do
    local ok, _ = pcall(function()
      local dev = renoise.Midi.create_output_device(out_name)
      table.insert(M.midi_outputs, dev)
    end)
  end

  if #M.midi_inputs == 0 or #M.midi_outputs == 0 then 
    M.disconnect()
    return false, "MIDI connection failed." 
  end

  -- Redundant Handshake for Mac Stability
  M.send_sysex(C.SYSEX_USER_MODE)
  M.send_sysex(C.SYSEX_USER_MODE)
  M.send_sysex(C.SYSEX_USER_MODE)
  
  M.flush_hardware(true)
  M.test_grid()
  
  -- Force initialize all buttons to visible (Value 1)
  M.init_all_buttons(1)
  
  display_buffer = {"  PUSH 1 — RENOISE", "  ----------------", "  DUAL-PORT ACTIVE", "  Buttons + LCD Linked"}
  led_state = {}
  btn_state = {}
  display_state = {nil, nil, nil, nil}
  M.flush_hardware()
  
  return true, table.concat(status_parts, "+")
end

function M.init_all_buttons(val)
  for i=0,121 do
    M.set_button_led(i, val)
  end
end

function M.test_grid()
  for i=36,99 do
    M.set_pad_led(i, 3) -- Bright Amber
  end
  M.flush_hardware(true)
end

function M.disconnect()
  for _, dev in ipairs(M.midi_outputs) do pcall(function() dev:close() end) end
  M.midi_outputs = {}
  for _, dev in ipairs(M.midi_inputs) do pcall(function() dev:close() end) end
  M.midi_inputs = {}
end

function M.is_connected()
  return #M.midi_inputs > 0 and #M.midi_outputs > 0
end

function M._on_raw_midi(message, port_name)
  M.traffic_count = M.traffic_count + 1
  local status   = message[1]
  local data1    = message[2] or 0
  local data2    = message[3] or 0
  local msg_type = bit.band(status, 0xF0)
  
  -- DEBUG: Print all CCs to verify mapping
  if msg_type == 0xB0 then
    print(string.format("[Push MIDI RAW] CC: %d Value: %d", data1, data2))
  end
  
  local debug_str = string.format("[%s] %02X %02X %02X", port_name:match("([^ ]+)$") or port_name:sub(-10), status, data1, data2)
  log_monitor(debug_str)
  print(debug_str)

  if not M.on_message_callback then return end

  local channel  = bit.band(status, 0x0F) + 1
  local parsed = { 
    raw = message, channel = channel, type = msg_type, 
    port = port_name, kind = "??", id = data1 
  }

  if msg_type == 0x90 then
    parsed.kind = (data2 > 0) and "note_on" or "note_off"
    parsed.note = data1; parsed.velocity = data2
    local row, col = C.note_to_pad(data1)
    if row then parsed.is_pad = true; parsed.pad_row = row; parsed.pad_col = col end
    parsed.id = data1
  elseif msg_type == 0x80 then
    parsed.kind = "note_off"; parsed.note = data1; parsed.velocity = data2
    parsed.id = data1
  elseif msg_type == 0xB0 then
    parsed.kind = "cc"; parsed.cc = data1; parsed.value = data2
    parsed.id = data1
    for i, cc in ipairs(C.ENCODER_CC) do
      if cc == data1 then
        parsed.is_encoder = true; parsed.encoder_index = i
        parsed.encoder_delta = C.encoder_delta(data2)
        break
      end
    end
  end

  pcall(function() M.on_message_callback(parsed) end)
end

function M.get_traffic() return M.traffic_count end

function M.get_monitor_log() return monitor_log end

local function raw_send(msg)
  if #M.midi_outputs == 0 or not msg then return end
  
  -- Sanitization for ALSA/Linux stability
  local clean_msg = {}
  for i, v in ipairs(msg) do
    local n = tonumber(v) or 0
    -- Boundary bytes (F0, F7) are allowed to be 0x80+
    if i == 1 or i == #msg then
      clean_msg[i] = bit.band(math.floor(n), 0xFF)
    else
      -- DATA bytes MUST be 7-bit (0-127) or ALSA/Renoise will CRASH
      clean_msg[i] = bit.band(math.floor(n), 0x7F)
    end
  end

  for _, out in ipairs(M.midi_outputs) do
    pcall(function() out:send(clean_msg) end)
  end
end

function M.send_note(channel, note, velocity)
  local c = bit.band(math.floor(tonumber(channel) or 1) - 1, 0x0F)
  local n = bit.band(math.floor(tonumber(note) or 0), 0x7F)
  local v = bit.band(math.floor(tonumber(velocity) or 0), 0x7F)
  local st = (v > 0) and 0x90 or 0x80
  raw_send({ bit.bor(st, c), n, v })
end

function M.send_cc(channel, cc, value)
  local c = bit.band(math.floor(tonumber(channel) or 1) - 1, 0x0F)
  local n = bit.band(math.floor(tonumber(cc) or 0), 0x7F)
  local v = bit.band(math.floor(tonumber(value) or 0), 0x7F)
  raw_send({ bit.bor(0xB0, c), n, v })
end

function M.send_sysex(data)
  if type(data) ~= "table" then return end
  raw_send(data)
end

function M.set_pad_led(note, color)
  if not note then return end
  led_buffer[note] = bit.band(math.floor(color or 0), 0x7F)
end

function M.set_button_led(cc, color)
  if not cc then return end
  btn_buffer[cc] = bit.band(math.floor(color or 0), 0x7F)
end

function M.set_grid_led(row, col, color)
  M.set_pad_led(C.pad_to_note(row, col), color)
end

function M.write_display(line, text)
  if line >= 1 and line <= 4 then display_buffer[line] = tostring(text or "") end
end

function M.write_display_all(lines)
  for i=1,4 do M.write_display(i, lines[i]) end
end

function M.clear_all_leds()
  led_buffer = {}
  btn_buffer = {}
  for i=0,127 do 
    led_buffer[i] = 0 
    btn_buffer[i] = 0
  end
end

function M.flush_hardware(force)
  if #M.midi_outputs == 0 then return end
  
  local sent_count = 0
  local MAX_SENT = 40 -- Throttle for Mac/ALSA stability
  
  -- 1. Flush PAD LEDs (Notes)
  for note, color in pairs(led_buffer) do
    if force or led_state[note] ~= color then
      led_state[note] = color
      M.send_note(1, note, color)
      sent_count = sent_count + 1
      if not force and sent_count >= MAX_SENT then return end
    end
  end
  
  -- 2. Flush BUTTON LEDs (CCs)
  for cc, color in pairs(btn_buffer) do
    if force or btn_state[cc] ~= color then
      btn_state[cc] = color
      M.send_cc(1, cc, color)
      sent_count = sent_count + 1
      if not force and sent_count >= MAX_SENT then return end
    end
  end
  
  -- 3. Flush LCD Display (SysEx)
  for i = 1, 4 do
    if force or display_buffer[i] ~= display_state[i] then
      display_state[i] = display_buffer[i]
      M.send_sysex(C.make_display_sysex(i, display_state[i]))
    end
  end
end

return M
