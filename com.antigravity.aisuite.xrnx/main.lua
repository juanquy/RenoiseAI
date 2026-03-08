-- main.lua
-- Renoise AI Suite: The Ultimate Electronic Music Tracker AI
-- Version 2.0 (Strict MIDI & Native Pattern Generation)

local json = require "json"

local options = renoise.Document.create("ScriptingToolPreferences") {
  server_url = "http://127.0.0.1:5000",
  api_key = "my_super_secret_proxmox_key",
  ollama_url = "http://127.0.0.1:11434/api/chat",
  ollama_model = "llama3.1"
}

renoise.tool().preferences = options

--------------------------------------------------------------------------------
-- Core Async Helpers
--------------------------------------------------------------------------------

-- Try to load the standard Renoise HTTP library
pcall(require, "renoise.http.request")

local function renoise_http_async(url, method, payload, is_json, callback)
  -- FORCE LOCALHOST: Purge any old remote IP references
  url = url:gsub("192.168.200.121", "127.0.0.1")
  
  print("[AI HTTP Request]:", method, url)

  -- Use tool's folder for temp files to avoid /tmp permission issues
  local tool_path = renoise.tool().bundle_path
  local res_file = tool_path .. "http_res.tmp"
  local err_file = tool_path .. "http_err.tmp"
  local done_file = tool_path .. "http_done.tmp"
  
  os.remove(done_file)
  
  local auth_h = string.format("-H 'X-API-Key: %s'", options.api_key.value)
  local body_arg = ""
  local temp_req = nil
  
  if is_json then
    temp_req = tool_path .. "http_req.json"
    local f = io.open(temp_req, "w")
    f:write(payload)
    f:close()
    body_arg = string.format("-H 'Content-Type: application/json' -d '@%s'", temp_req)
  elseif method == "POST" and payload then
    -- payload is a filepath
    body_arg = string.format("-F 'file=@%s'", payload)
  end

  local cmd = string.format("( curl -sS -L -X %s %s %s '%s' > '%s' 2> '%s' ; touch '%s' ) &", 
                             method, auth_h, body_arg, url, res_file, err_file, done_file)
  
  os.execute(cmd)
  
  local function poll()
    local f = io.open(done_file, "r")
    if f then
      f:close()
      renoise.tool():remove_timer(poll)
      
      local res_f = io.open(res_file, "r")
      local res = res_f and res_f:read("*a") or ""
      if res_f then res_f:close() end
      
      local err_f = io.open(err_file, "r")
      local err = err_f and err_f:read("*a") or ""
      if err_f then err_f:close() end
      
      if err and err ~= "" then
        print("[AI HTTP Curl Log]:", err)
      end
      
      -- Cleanup
      os.remove(done_file)
      os.remove(res_file)
      os.remove(err_file)
      if temp_req then os.remove(temp_req) end
      
      if callback then callback(res) end
    end
  end
  
  renoise.tool():add_timer(poll, 500)
end

--------------------------------------------------------------------------------
-- The AI Brain (Electronic Music Specific)
--------------------------------------------------------------------------------

local SYSTEM_PROMPT = [[
You are an expert Electronic Music AI composer controlling the Renoise DAW Tracker.
Your sole purpose is to invent structurally sound, fierce, and authentic electronic music (Techno, House, Cyberpunk, D&B).

Always respond ONLY in standard JSON format containing a list of `commands` that Renoise will execute.
Never include conversational text outside the JSON.
Electronic music requires 4-to-the-floor rhythms, driving syncopated basslines, and hypnotic synth hooks.

CRITICAL RENOISE RULES:
1. All Track Indices must start at 0 (e.g., track 0 is the first track, track 1 is the second).
2. All notes MUST strictly follow the format "Note-Octave" with exactly 3 characters.
   - Example Valid Notes: "C-4", "D#4", "G-3", "A#2", "OFF"
   - EXTREMELY INVALID NOTES: "D#-4" (4 characters), "Db4" (flats not allowed), "C4" (missing hyphen).
   - If a note has a sharp, it must be exactly like "C#4". If it does not, it must use a hyphen, like "C-4".
3. Use `add_track` to create new functional electronic instruments (e.g., "909 Drums", "Sub Bass", "Acid Lead").
4. Volume must be between 00 and 7F (Hex). Default 7F.
5. The tracker lines run rapidly. Separate drum hits by 4-8 lines to maintain a steady tempo.

AVAILABLE COMMANDS:
`{"type": "add_track", "track": <index>, "name": "<instrument_string>"}`
`{"type": "clear_track", "track": <index>}`
`{"type": "set_note", "track": <index>, "line": <integer>, "note": "<3_char_note_string>", "volume": "<hex_volume>", "instrument": <integer>}`
`{"type": "note_off", "track": <index>, "line": <integer>}`
`{"type": "set_bpm", "bpm": <integer>}`
`{"type": "set_lpb", "lpb": <integer>}`

EXAMPLE (Basic Techno Groove):
{
  "commands": [
    {"type": "set_bpm", "bpm": 135},
    {"type": "set_lpb", "lpb": 4},
    {"type": "add_track", "track": 0, "name": "909 Drums"},
    {"type": "add_track", "track": 1, "name": "Rolling Sub Bass"},
    {"type": "add_track", "track": 2, "name": "Cyberpunk Lead"},
    {"type": "set_note", "track": 0, "line": 0, "note": "C-4", "volume": "7F", "instrument": 0},
    {"type": "set_note", "track": 0, "line": 4, "note": "C-4", "volume": "7F", "instrument": 0},
    {"type": "set_note", "track": 0, "line": 8, "note": "C-4", "volume": "7F", "instrument": 0},
    {"type": "set_note", "track": 0, "line": 12, "note": "C-4", "volume": "7F", "instrument": 0},
    {"type": "set_note", "track": 1, "line": 2, "note": "D-2", "volume": "50", "instrument": 1},
    {"type": "set_note", "track": 1, "line": 6, "note": "D-2", "volume": "50", "instrument": 1},
    {"type": "set_note", "track": 2, "line": 0, "note": "G-5", "volume": "60", "instrument": 2},
    {"type": "note_off", "track": 2, "line": 8}
  ]
}
]]

local chat_history = {
  { role = "system", content = SYSTEM_PROMPT }
}

--------------------------------------------------------------------------------
-- AI Command Executor
--------------------------------------------------------------------------------

local function execute_command(cmd)
  local song = renoise.song()
  
  if cmd.type == "add_track" then
    local new_track_idx = cmd.track + 1
    if new_track_idx <= song.sequencer_track_count then
      song:track(new_track_idx).name = cmd.name or string.format("Track %02d", new_track_idx)
    else
      local track = song:insert_track_at(new_track_idx)
      track.name = cmd.name or string.format("Track %02d", new_track_idx)
    end
    -- Auto-instantiate a dummy instrument to hold the MIDI notes
    if new_track_idx > #song.instruments then
      local inst = song:insert_instrument_at(new_track_idx)
      inst.name = cmd.name or "AI Synth"
    else
      song.instruments[new_track_idx].name = cmd.name or "AI Synth"
    end
    
  elseif cmd.type == "clear_track" then
    local idx = cmd.track + 1
    if idx <= song.sequencer_track_count then
      for _, pos in ipairs(song.sequencer.pattern_sequence) do
        local p = song:pattern(pos)
        p:track(idx):clear()
      end
    end

  elseif cmd.type == "set_bpm" then
    song.transport.bpm = cmd.bpm

  elseif cmd.type == "set_lpb" then
    song.transport.lpb = cmd.lpb

  elseif cmd.type == "set_note" or cmd.type == "note_off" then
    local absolute_line = cmd.line + 1
    local track_idx = cmd.track + 1
    local target_track = song:track(track_idx)
    
    if not target_track then return end
    target_track.visible_note_columns = 1
    
    local current_seq_idx = 1
    local local_line = absolute_line
    
    while true do
      if current_seq_idx > #song.sequencer.pattern_sequence then
        song.sequencer:insert_new_pattern_at(current_seq_idx)
      end
      
      local pattern_idx = song.sequencer:pattern(current_seq_idx)
      local pattern = song:pattern(pattern_idx)
      local pat_lines = pattern.number_of_lines
      
      if local_line <= pat_lines then
        local note_col = pattern:track(track_idx).lines[local_line]:note_column(1)
        
        if cmd.type == "note_off" then
          note_col.note_value = 120 -- OFF
        else
          -- EXTREME NOTE SANITIZATION
          local raw_note = cmd.note:upper()
          
          -- Remove invalid flats or inject missing hyphens for 3-character format
          raw_note = raw_note:gsub("BB", "A")
          raw_note = raw_note:gsub("EB", "D")
          raw_note = raw_note:gsub("AB", "G")
          raw_note = raw_note:gsub("DB", "C")
          raw_note = raw_note:gsub("GB", "F")
          
          -- Ensure hyphen exists if no sharp
          if #raw_note == 2 and not raw_note:find("#") then
            raw_note = raw_note:sub(1,1) .. "-" .. raw_note:sub(2,2)
          end
          
          -- Last resort fallback if length is wrong
          if #raw_note > 3 and raw_note:find("#%-") then
            raw_note = raw_note:gsub("%-", "")
          end
          
          if #raw_note > 3 then raw_note = raw_note:sub(1,3) end
          
          note_col.note_string = raw_note
          note_col.volume_string = cmd.volume or "7F"
          -- Ensure valid instrument assignment (Renoise expects 0-indexed values in Lua mapping, UI displays it +1)
          local safe_inst = cmd.instrument or cmd.track
          note_col.instrument_value = math.max(0, math.min(254, safe_inst))
        end
        break
      else
        local_line = local_line - pat_lines
        current_seq_idx = current_seq_idx + 1
      end
    end
  end
end

--------------------------------------------------------------------------------
-- Ollama Chat Composer UI
--------------------------------------------------------------------------------

local function compose_with_ai()
  local view = renoise.app().window
  local vb = renoise.ViewBuilder()
  
  local response_list = vb:multiline_textfield { id = "response_list", width = 580, height = 300, text = "" }
  local prompt_input = vb:textfield { id = "prompt_input", width = 480, height = 30 }
  
  for _, msg in ipairs(chat_history) do
    if msg.role ~= "system" then
      response_list:add_line(string.format("[%s]: %s", msg.role:upper(), msg.content))
    end
  end
  
  local function parse_and_execute_json(json_str)
    local ok, data = pcall(json.decode, json_str)
    if ok and data and data.commands then
      for _, cmd in ipairs(data.commands) do
        local ex_ok, err = pcall(execute_command, cmd)
        if not ex_ok then print("[AI Executor Error]:", err) end
      end
      return true
    end
    return false
  end

  local function send_chat()
    local user_text = prompt_input.text
    if user_text == "" then return end
    
    prompt_input.text = ""
    response_list:add_line("[USER]: " .. user_text)
    
    table.insert(chat_history, { role = "user", content = user_text })
    
    local payload = {
      model = options.ollama_model.value,
      messages = chat_history,
      stream = false,
      format = "json"
    }
    
    local json_body = json.encode(payload)
    
    renoise_http_async(options.ollama_url.value, "POST", json_body, true, function(res)
      if res and res ~= "" then
        local ok, data = pcall(json.decode, res)
        if ok and data and data.message and data.message.content then
          local ai_text = data.message.content
          response_list:add_line("[AI Composer (JSON Generated)]:")
          response_list:add_line(ai_text)
          
          -- Execute the commands
          parse_and_execute_json(ai_text)
          
          table.insert(chat_history, { role = "assistant", content = ai_text })
        else
          response_list:add_line("[ERR]: Invalid JSON received from Ollama.")
        end
      else
        response_list:add_line("[ERR]: No response from Ollama. Ensure the server is running.")
      end
      response_list:scroll_to_last_line()
    end)
  end
  
  local dialog_content = vb:column {
    margin = 10,
    spacing = 10,
    vb:text { text = "AI Companion (Ollama LLM). Describe what you want the sequencer to do:" },
    response_list,
    vb:row {
      spacing = 10,
      prompt_input,
      vb:button {
        text = "Send",
        width = 90,
        height = 30,
        notifier = send_chat
      }
    }
  }
  
  renoise.app():show_custom_dialog("Compose with AI Tracking", dialog_content)
end

--------------------------------------------------------------------------------
-- Audio to Tracker (MIDI & Stems) Processing
--------------------------------------------------------------------------------

local function write_midi_notes_to_track(track_idx, notes_array, instr_idx)
  local async_song = renoise.song()
  local bpm = async_song.transport.bpm
  local lpb = async_song.transport.lpb
  local lines_per_sec = (bpm * lpb) / 60.0

  for _, note in ipairs(notes_array) do
    local absolute_line = math.floor(note.start * lines_per_sec) + 1
    local renoise_note = math.max(0, math.min(119, note.note - 12))
    local vol = math.min(127, note.velocity)
    
    local current_seq_idx = 1
    local local_line = absolute_line
    
    while true do
      if current_seq_idx > #async_song.sequencer.pattern_sequence then
        async_song.sequencer:insert_new_pattern_at(current_seq_idx)
      end
      
      local pattern_idx = async_song.sequencer:pattern(current_seq_idx)
      local pattern = async_song:pattern(pattern_idx)
      local pat_lines = pattern.number_of_lines
      
      if local_line <= pat_lines then
        local note_col = pattern:track(track_idx).lines[local_line]:note_column(1)
        note_col.note_value = renoise_note
        note_col.instrument_value = instr_idx
        note_col.volume_value = vol
        break
      else
        local_line = local_line - pat_lines
        current_seq_idx = current_seq_idx + 1
      end
    end
  end
end

local function process_ai_audio_analysis_response(response_data)
  local async_song = renoise.song()
  
  -- 1. VOCAL EXCEPTION: Render Vocals strictly as Audio
  if response_data.stems and response_data.stems.vocals then
    renoise.app():show_status("AI Suite: Loading Vocal Audio Stem...")
    local url = response_data.stems.vocals
    local dict_temp = os.tmpname() .. ".wav"
    os.execute(string.format('curl -s -L -H "X-API-Key: %s" "%s" -o "%s" > /dev/null 2>&1', options.api_key.value, url, dict_temp))
    
    local instr = async_song:insert_instrument_at(#async_song.instruments + 1)
    instr.name = "Audio Stem: Vocals"
    if #instr.samples == 0 then instr:insert_sample_at(1) end
    instr.samples[1].sample_buffer:load_from(dict_temp)
    os.remove(dict_temp)
    
    local new_track_idx = async_song.sequencer_track_count + 1
    local track = async_song:insert_track_at(new_track_idx)
    track.name = "Vocals (Audio)"
    track.visible_note_columns = 1
    
    local smp = instr.samples[1]
    smp.autoseek = true
    
    local first_pat_idx = async_song.sequencer:pattern(1)
    local note_col = async_song:pattern(first_pat_idx):track(new_track_idx).lines[1]:note_column(1)
    note_col.note_value = 48 -- C-4
    note_col.instrument_value = #async_song.instruments - 1
  end
  
  -- 2. MIDI PATTERN GENERATION: Everything else is strictly Notes
  if response_data.notes then
    local electronic_instruments = {
      drums = "AI Drums (909)",
      bass = "AI Sub Bass",
      melody = "AI Lead Synth",
      piano = "AI Chords",
      other = "AI Pad/FX"
    }

    for category, notes in pairs(response_data.notes) do
      if #notes > 0 then
        renoise.app():show_status("AI Suite: Writing MIDI Notes for: " .. category)
        
        local new_track_idx = async_song.sequencer_track_count + 1
        local track = async_song:insert_track_at(new_track_idx)
        track.name = "MIDI: " .. category:gsub("^%l", string.upper)
        track.visible_note_columns = 1
        
        local instr_name = electronic_instruments[category] or ("AI " .. category)
        local instr = async_song:insert_instrument_at(#async_song.instruments + 1)
        instr.name = instr_name
        
        write_midi_notes_to_track(new_track_idx, notes, #async_song.instruments - 1)
      end
    end
  end
  
  renoise.app():show_status("AI Suite: Multi-Track Import & Transcription Complete!")
end

local function pick_file_and_upload(endpoint_path, status_msg)
  local filepath = renoise.app():prompt_for_filename_to_read({"*.wav", "*.flac", "*.mp3"}, "Select Audio File for AI Analysis")
  if filepath == "" then return end
  
  renoise.app():show_status(status_msg)
  
  renoise_http_async(options.server_url.value .. endpoint_path, "POST", filepath, false, function(raw_response)
    if not raw_response or raw_response == "" then
      renoise.app():show_status("AI Suite: Server Error during processing.")
      return
    end
    
    local ok, response_data = pcall(json.decode, raw_response)
    if not ok or not response_data or response_data.status ~= "success" then
      renoise.app():show_error("AI Suite: Processing failed or invalid JSON returned.")
      print("Raw Server Response:", raw_response)
      return
    end
    
    renoise.app():show_status("AI Suite: Analysis complete! Constructing Renoise Sequence...")
    process_ai_audio_analysis_response(response_data)
  end)
end

local function import_and_split_song()
  pick_file_and_upload("/transcribe_full", "AI Suite: Uploading Song for Stem Splitting & Full MIDI Transcription... (This will take minutes!)")
end

local function import_single_stem_to_midi()
  pick_file_and_upload("/transcribe", "AI Suite: Uploading single stem for pure MIDI extraction... (Takes approx 30-60 secs)")
end

local function configure_api_preferences()
  local vb = renoise.ViewBuilder()
  local dialog_content = vb:column {
    margin = 15,
    spacing = 10,
    vb:text { text = "AI Backend Server (Demucs / YourMT3+):" },
    vb:textfield { id = "ai_server_url", width = 300, bind = options.server_url },
    vb:text { text = "API Key:" },
    vb:textfield { id = "api_key", width = 300, bind = options.api_key },
    vb:space { height = 10 },
    vb:text { text = "Local Ollama LLM (AI Composition Engine):" },
    vb:textfield { id = "ollama_url", width = 300, bind = options.ollama_url },
    vb:text { text = "Ollama Model:" },
    vb:textfield { id = "ollama_model", width = 300, bind = options.ollama_model },
    vb:space { height = 15 },
    vb:text { text = "Changes save automatically upon closing." }
  }
  renoise.app():show_custom_dialog("AI Suite Preferences", dialog_content)
end

--------------------------------------------------------------------------------
-- UI Tool Registration
--------------------------------------------------------------------------------

-- Main Menu
renoise.tool():add_menu_entry {
  name = "Main Menu:Tools:AI Integration:Compose Track with AI (Ollama)...",
  invoke = compose_with_ai
}

renoise.tool():add_menu_entry {
  name = "Main Menu:Tools:AI Integration:Import & Split Audio (Song -> Multi-track MIDI)...",
  invoke = import_and_split_song
}

renoise.tool():add_menu_entry {
  name = "Main Menu:Tools:AI Integration:Convert Single Stem -> MIDI...",
  invoke = import_single_stem_to_midi
}

renoise.tool():add_menu_entry {
  name = "Main Menu:Tools:AI Integration:Preferences...",
  invoke = configure_api_preferences
}

-- Context Menus (Right Click)
renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Compose Track with AI (Ollama)...",
  invoke = compose_with_ai
}

renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Import & Split Audio...",
  invoke = import_and_split_song
}

renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Convert Single Stem -> MIDI...",
  invoke = import_single_stem_to_midi
}

renoise.tool():add_menu_entry {
  name = "Sample Editor:AI Integration:Convert Sample -> MIDI...",
  invoke = import_single_stem_to_midi
}

print("AI Suite initialized. Native MIDI generation primed.")
