-- main.lua
-- Renoise AI Suite: The Ultimate Electronic Music Tracker AI
-- Version 2.0 (Strict MIDI & Native Pattern Generation)

local json = require "json"

local options = renoise.Document.create("ScriptingToolPreferences") {
  server_url = "http://127.0.0.1:5055",
  api_key = "my_super_secret_proxmox_key"
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
  
  local req_id = tostring(os.clock()):gsub("%.", "") .. tostring(math.random(1000, 9999))
  
  -- Use tool's folder for temp files to avoid /tmp permission issues
  local tool_path = renoise.tool().bundle_path
  local res_file = tool_path .. "http_res_" .. req_id .. ".tmp"
  local err_file = tool_path .. "http_err_" .. req_id .. ".tmp"
  local done_file = tool_path .. "http_done_" .. req_id .. ".tmp"
  
  os.remove(done_file)
  
  local auth_h = string.format("-H 'X-API-Key: %s'", options.api_key.value)
  local body_arg = ""
  local temp_req = nil
  
  if is_json then
    temp_req = tool_path .. "http_req_" .. req_id .. ".json"
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
-- Status Notification Dialog
--------------------------------------------------------------------------------

local status_dialog = nil
local status_view = nil

local function show_ai_status_dialog(initial_message)
  local vb = renoise.ViewBuilder()
  
  if status_dialog and status_dialog.visible then
    status_view.text = initial_message
    return
  end
  
  status_view = vb:text {
    text = initial_message,
    width = 400,
    align = "center",
    font = "big"
  }
  
  local content = vb:column {
    margin = 20,
    spacing = 10,
    vb:horizontal_aligner {
      mode = "center",
      vb:text { text = "🤖 AI Suite: Processing Data...", font = "bold" }
    },
    vb:horizontal_aligner {
      mode = "center",
      status_view
    },
    vb:horizontal_aligner {
      mode = "center",
      vb:text { text = "(This window will close automatically when finished)" }
    }
  }
  
  status_dialog = renoise.app():show_custom_dialog("AI Suite Status", content)
end

local function update_ai_status(new_message)
  if status_dialog and status_dialog.visible and status_view then
    status_view.text = new_message
  end
  renoise.app():show_status("AI Suite: " .. new_message)
end

local function close_ai_status_dialog()
  if status_dialog and status_dialog.visible then
    status_dialog:close()
  end
end

--------------------------------------------------------------------------------
-- The AI Brain (Electronic Music Specific)
--------------------------------------------------------------------------------

local SYSTEM_PROMPT = [[
You are an expert Electronic Music AI composer/arranger controlling Renoise.
Your goal is to build FULL arrangements (Intro, Build, Drop, Outro).

STRUCTURAL THINKING:
- First, call `init_arrangement` to set up the timeline (e.g. 8 or 16 patterns).
- Use `add_pattern` and `clone_pattern` to build the sections.
- Use `set_pattern_name` to label sections (e.g., "INTRO", "THE DROP").
- Use `fill_sequence` to copy a drum loop across multiple patterns.
- Evolution: Use `set_track_volume` or note variations to keep the song "alive".

CRITICAL RENOISE RULES:
1. Track Indices start at 0. Pattern Indices start at 0.
2. Notes must be 3 characters: "C-4", "D#4", "G-3", "OFF".
3. Use `add_track` to create roles: "Kick", "Sub Bass", "Main Lead".

AVAILABLE COMMANDS:
`{"type": "init_arrangement", "patterns": <int>}` - Wipes and prepares the sequence.
`{"type": "add_track", "track": <index>, "name": "<string>"}`
`{"type": "set_bpm", "bpm": <integer>}`
`{"type": "add_pattern", "name": "<string>"}`
`{"type": "clone_pattern", "source": <index>, "name": "<string>"}`
`{"type": "set_pattern_name", "index": <index>, "name": "<string>"}`
`{"type": "fill_sequence", "source": <int>, "dest": <int>, "track": <int>}` - Copies track content from source pattern to dest pattern.
`{"type": "set_track_volume", "track": <int>, "volume": <float>}` - 0.0 to 1.0.
`{"type": "set_note", "track": <index>, "line": <absolute_line>, "note": "<3_char>", "volume": "<hex>", "instrument": <int>}`
`{"type": "note_off", "track": <index>, "line": <absolute_line>}`

EXAMPLE (Suno-Style Full Arrangement):
{
  "commands": [
    {"type": "init_arrangement", "patterns": 8},
    {"type": "set_bpm", "bpm": 128},
    {"type": "add_track", "track": 0, "name": "Kick"},
    {"type": "set_pattern_name", "index": 0, "name": "INTRO"},
    {"type": "set_note", "track": 0, "line": 0, "note": "C-4"},
    {"type": "fill_sequence", "source": 0, "dest": 1, "track": 0},
    {"type": "fill_sequence", "source": 0, "dest": 4, "track": 0},
    {"type": "set_track_volume", "track": 0, "volume": 0.5}
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
      -- Only rename if the track name is generic/empty
      local current_name = song:track(new_track_idx).name
      if current_name == "" or current_name:find("Track %d+") then
        song:track(new_track_idx).name = cmd.name or current_name
      end
    else
      local track = song:insert_track_at(new_track_idx)
      track.name = cmd.name or string.format("Track %02d", new_track_idx)
    end

    -- Handle instrument assignment/matching
    local target_inst_idx = cmd.instrument_index
    if target_inst_idx then
      -- Conductor already matched this to an existing instrument
      -- Ensure the track is actually assigned to this instrument (Renoise tracks point to instruments)
      -- Note: In Renoise, notes in the pattern have an instrument index. 
      -- The track doesn't "own" an instrument strictly, but for AI we conceptually link them.
      print(string.format("AI Suite: Mapping track %d to instrument %d", new_track_idx, target_inst_idx))
    else
      -- Fallback: If no mapping provided, and we are adding a track, check if we should create a slot
      if new_track_idx > #song.instruments then
        local inst = song:insert_instrument_at(new_track_idx)
        inst.name = cmd.name or "AI Instrument"
      end
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

  elseif cmd.type == "add_pattern" then
    local new_idx = #song.sequencer.pattern_sequence + 1
    song.sequencer:insert_new_pattern_at(new_idx)
    if cmd.name then
      local pat_idx = song.sequencer:pattern(new_idx)
      song:pattern(pat_idx).name = cmd.name
    end

  elseif cmd.type == "clone_pattern" then
    local src_idx = (cmd.source or 0) + 1
    if src_idx <= #song.sequencer.pattern_sequence then
      local new_idx = #song.sequencer.pattern_sequence + 1
      song.sequencer:clone_pattern_at(src_idx, new_idx)
      if cmd.name then
        local pat_idx = song.sequencer:pattern(new_idx)
        song:pattern(pat_idx).name = cmd.name
      end
    end

  elseif cmd.type == "set_pattern_name" then
    local idx = (cmd.index or 0) + 1
    if idx <= #song.sequencer.pattern_sequence then
      local pat_idx = song.sequencer:pattern(idx)
      song:pattern(pat_idx).name = cmd.name or "Section"
    end

  elseif cmd.type == "init_arrangement" then
    while #song.sequencer.pattern_sequence > 1 do
      song.sequencer:remove_sequence_at(2)
    end
    -- Fix: handle case where patterns might be a string or table from AI
    local num_patterns = cmd.patterns
    if type(num_patterns) == "table" then num_patterns = num_patterns[1] end
    num_patterns = tonumber(num_patterns) or 8
    
    for i = 1, num_patterns - 1 do
      song.sequencer:insert_new_pattern_at(i + 1)
    end

  elseif cmd.type == "set_pattern_length" then
    -- cmd.index = 0-based sequencer slot, cmd.lines = number of lines
    local seq_idx = (cmd.index or 0) + 1
    if seq_idx <= #song.sequencer.pattern_sequence then
      local pat_idx = song.sequencer:pattern(seq_idx)
      song:pattern(pat_idx).number_of_lines = math.max(1, cmd.lines or 32)
    end

  elseif cmd.type == "fill_sequence" then
    local src_idx = (cmd.source or 0) + 1
    local dest_idx = (cmd.dest or 0) + 1
    local track_idx = (cmd.track or 0) + 1
    if src_idx <= #song.sequencer.pattern_sequence and dest_idx <= #song.sequencer.pattern_sequence then
      local src_pat = song:pattern(song.sequencer:pattern(src_idx))
      local dest_pat = song:pattern(song.sequencer:pattern(dest_idx))
      dest_pat:track(track_idx):copy_from(src_pat:track(track_idx))
    end

  elseif cmd.type == "set_track_volume" then
    local idx = (cmd.track or 0) + 1
    if idx <= song.sequencer_track_count then
      song:track(idx).prefx_volume.value = cmd.volume or 1.0
    end

  elseif cmd.type == "set_note" or cmd.type == "note_off" then
    local track_idx = cmd.track + 1
    local target_track = song:track(track_idx)

    if not target_track then return end
    target_track.visible_note_columns = 1

    -- NEW: explicit pattern + local line addressing.
    -- cmd.pattern  = 0-based sequencer slot index (which section)
    -- cmd.line     = 0-based line WITHIN that pattern
    local seq_idx = (cmd.pattern or 0) + 1
    local local_line = cmd.line + 1  -- convert to 1-based

    if seq_idx <= #song.sequencer.pattern_sequence then
      local pattern_idx = song.sequencer:pattern(seq_idx)
      local pattern = song:pattern(pattern_idx)

      if local_line <= pattern.number_of_lines then
        local note_col = pattern:track(track_idx).lines[local_line]:note_column(1)

        if cmd.type == "note_off" then
          note_col.note_value = 120 -- OFF
        else
          -- NOTE SANITIZATION
          local raw_note = cmd.note:upper()
          raw_note = raw_note:gsub("BB", "A")
          raw_note = raw_note:gsub("EB", "D")
          raw_note = raw_note:gsub("AB", "G")
          raw_note = raw_note:gsub("DB", "C")
          raw_note = raw_note:gsub("GB", "F")
          if #raw_note == 2 and not raw_note:find("#") then
            raw_note = raw_note:sub(1,1) .. "-" .. raw_note:sub(2,2)
          end
          if #raw_note > 3 and raw_note:find("#%-") then
            raw_note = raw_note:gsub("%-", "")
          end
          if #raw_note > 3 then raw_note = raw_note:sub(1,3) end

          note_col.note_string = raw_note
          note_col.volume_string = cmd.volume or "7F"
          local safe_inst = cmd.instrument or cmd.track
          note_col.instrument_value = math.max(0, math.min(254, safe_inst))
        end
      end
    end
  elseif cmd.type == "execute_lua" then
    local code = cmd.code
    if code then
      local chunk, err = loadstring(code)
      if chunk then
        local ok, res = pcall(chunk)
        if not ok then
          renoise.app():show_status("AI Lua Error: " .. tostring(res))
        end
      else
        renoise.app():show_status("AI Lua Syntax Error: " .. tostring(err))
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
  
  local response_list = vb:multiline_textfield { id = "response_list", width = 580, height = 250, text = "" }
  local prompt_input = vb:multiline_textfield { id = "prompt_input", width = 480, height = 70, text = "" }
  local lyrics_input = vb:multiline_textfield { id = "lyrics_input", width = 480, height = 40, text = "" }
  
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
    
    local final_prompt = user_text
    local lyrics_text = lyrics_input.text
    if lyrics_text and lyrics_text ~= "" then
      final_prompt = final_prompt .. "\n[LYRICS]:\n" .. lyrics_text
    end
    
    prompt_input.text = ""
    lyrics_input.text = ""
    response_list:add_line("[USER]: " .. final_prompt)
    
    table.insert(chat_history, { role = "user", content = final_prompt })
    
    local song_length_idx = vb.views.song_length_selector.value
    local song_lengths = {4, 8, 12, 16, 24, 32, 48, 64}
    local selected_length = song_lengths[song_length_idx] or 16
    
    local inst_list = {}
    for i = 1, #renoise.song().instruments do
      local inst = renoise.song().instruments[i]
      local has_content = #inst.samples > 0 or (inst.plugin_properties and inst.plugin_properties.plugin_device ~= nil)
      if inst.name ~= "" or has_content then
        table.insert(inst_list, { 
          index = i-1, 
          name = (inst.name ~= "" and inst.name or ("Slot " .. tostring(i-1))) 
        })
      end
    end

    local payload = {
      messages = chat_history,
      stream = false,
      format = "json",
      song_length = selected_length,
      instruments = inst_list
    }
    
    local json_body = json.encode(payload)
    
    renoise.app():show_status("AI Suite: Neural Engine is dreaming up a track...")
    
    local target_url = options.server_url.value .. "/compose_native_midi"
    
    renoise_http_async(target_url, "POST", json_body, true, function(res)
      renoise.app():show_status("AI Suite: Parsing Neural MIDI commands...")
      if res and res ~= "" then
        local ok, data = pcall(json.decode, res)
        if ok and data then
          if data.commands or (data.status == "pending" and data.task_id) then
             response_list:add_line("[Neural Engine]: Sequence requested. Processing on GPU...")
             if data.task_id then
                poll_task_status(data.task_id, function(final_data)
                   if final_data.commands and #final_data.commands > 0 then
                      local count = 0
                      for _, cmd in ipairs(final_data.commands) do
                        execute_command(cmd)
                        count = count + 1
                      end
                      response_list:add_line(string.format("[Neural Engine]: Generated %d commands. Arrangement applied!", count))
                   else
                      response_list:add_line("[Neural Engine]: Error: 0 valid notes returned.")
                   end
                end)
             end
          else
            response_list:add_line("[ERR]: Unknown response format.")
          end
        else
          response_list:add_line("[ERR]: Invalid JSON received.")
        end
      else
        response_list:add_line("[ERR]: No response. Ensure the server is running on Port 5055.")
      end
      response_list:scroll_to_last_line()
    end)
  end
  
  local prompt_gallery = {
    "--- Select a Style ---",
    "Heavy 135BPM Industrial Techno with distorted drums and acid synth.",
    "Liquid Drum & Bass with fast rolling breaks and a deep sub bass.",
    "90s Chicago House groove with groovy bass and piano stabs.",
    "Dark Cinematic Sci-Fi atmosphere with low drones and metallic clicks.",
    "Minimal Tech-House loop with tight drums and a bouncy sine wave bass.",
    "Aggressive Mid-tempo Cyberpunk chug with gravelly synth textures.",
    "Dreamy Lo-fi Hip Hop beat with soft dusty drums and a mellow Rhodes progression.",
    "Hard Psytrance sequence with galloping basslines at 145BPM.",
    "Melodic Progressive House with uplifting pads and a steady drive.",
    "Experimental Glitch hop with randomized percussion and organic sounds.",
    "Hardstyle Banger with aggressive distorted kicks and epic supersaw leads.",
    "Deep Minimal House with smooth chords and sophisticated percussion.",
    "Synthwave 80s Vibe with gated reverb drums and neon analog synth leads.",
    "Dark Ambient Soundscape focusing on textures, drones, and no drums.",
    "Future Bass with wobbly emotional synths and punchy half-time drums.",
    "Classic 90s Eurodance with high-energy bass and infectious synth melodies.",
    "Heavy Dubstep with aggressive growls and syncopated rhythmic bass movement.",
    "Filtered French House with funky disco samples and side-chained bass.",
    "Old School Jungle with complex amen break chops and deep sub-bass.",
    "Uplifting Trance with ethereal pads and driving 138BPM arpeggios.",
    "Atmospheric DnB: 170BPM with lush pads, rolling breakbeats, and a simple 808 sub.",
    "Neurofunk Banger: 172BPM with aggressive Reese bass modulation and tight technical drums.",
    "Jump-up DnB: 175BPM with high-energy screeching bass and a simple but heavy 2rd-step beat.",
    "Techstep Sequence: 170BPM with dark industrial stabs and cold, hard-hitting drum patterns.",
    "Ragga Jungle: 165BPM with classic sampled breaks, deep reggae-inspired sub bass, and chaotic percussion."
  }

  local dialog_content = vb:column {
    margin = 15,
    spacing = 12,
    
    -- Header Section
    vb:row {
      vb:text { text = "🧠 Neural MIDI Architect (Text2midi AAAI 2025)", font = "big", style = "strong" }
    },
    vb:text { text = "Mac Studio MPS Edition. Describe your desired arrangement below:", font = "italic" },
    
    -- Conversation Box
    response_list,
    
    -- Options Section
    vb:row {
      spacing = 8,
      vb:text { text = "💡 Inspiration:", font = "bold" },
      vb:popup {
        id = "gallery_selector",
        items = prompt_gallery,
        width = 460,
        notifier = function(idx)
          if idx > 1 then
            prompt_input.text = prompt_gallery[idx]
            send_chat()
          end
        end
      }
    },
    
    vb:row {
      spacing = 15,
      vb:text { text = "📏 Setup Patterns:", font = "bold" },
      vb:popup {
        id = "song_length_selector",
        items = {"4", "8", "12", "16", "24", "32", "48", "64"},
        value = 4 -- 16 patterns
      }
    },
    
    -- Input Section
    vb:row {
      spacing = 15,
      vb:column {
        spacing = 5,
        vb:text { text = "Director's Prompt:", font = "bold" },
        prompt_input,
        vb:text { text = "Additional Notes / Concepts:", font = "bold" },
        lyrics_input
      },
      vb:column {
        margin = 15,
        vb:button {
          text = "Generate\nSequence",
          width = 110,
          height = 130,
          color = {20, 150, 50}, -- Renoise custom button color support
          notifier = send_chat
        }
      }
    }
  }
  
  renoise.app():show_custom_dialog("AI Suite: Neural MIDI Architect", dialog_content)
end

--------------------------------------------------------------------------------
-- Audio to Tracker (MIDI & Stems) Processing
--------------------------------------------------------------------------------

local function process_ai_audio_analysis_response(response_data, is_append_only)
  local song = renoise.song()
  local bpm = song.transport.bpm
  local lpb = song.transport.lpb
  local lines_per_sec = (bpm * lpb) / 60.0
  
  local tracks_to_process = {}
  local current_state = "READY"
  local state_idx = 1
  
  -- Internal Helper: Micro-Task Scheduler
  local function run_task(task_fn, on_done)
    local function wrapper()
      local ok, finished = pcall(task_fn)
      if not ok then
        renoise.tool():remove_timer(wrapper)
        renoise.app():show_error("AI Suite Error during task: " .. tostring(finished))
      elseif not finished then
        renoise.tool():remove_timer(wrapper)
        if on_done then on_done() end
      end
    end
    renoise.tool():add_timer(wrapper, 10)
  end

  -- STEP 1: ASYNC PROJECT CLEANUP
  local function task_cleanup()
    if is_append_only then
      update_ai_status("Mode: Append. Pre-calculating note data...")
      current_state = "QUEUE_DATA"
      return false
    end
    
    if song.sequencer_track_count > 1 then
      song:delete_track_at(song.sequencer_track_count)
      return true
    end
    if #song.instruments > 1 then
      song:delete_instrument_at(#song.instruments)
      return true
    end
    song.instruments[1]:clear()
    song.instruments[1].name = "AI Instrument 1"
    if #song.instruments[1].samples == 0 then song.instruments[1]:insert_sample_at(1) end
    
    local pat_idx = 1
    local function clear_pats()
      if pat_idx > #song.patterns then return false end
      song:pattern(pat_idx):track(1):clear()
      pat_idx = pat_idx + 1
      return true
    end
    run_task(clear_pats, function()
      update_ai_status("Project Purged. Pre-calculating note data...")
      current_state = "QUEUE_DATA"
    end)
    return false -- Cleanup task itself is done, it started sub-tasks
  end

  -- STEP 2: ASYNC DATA PREPARATION & TRACK CREATION
  local function task_prepare_data()
    if not response_data.notes then return false end
    
    local categories = {}
    for cat, _ in pairs(response_data.notes) do table.insert(categories, cat) end
    local cat_idx = 1
    
    local function create_tracks_async()
      if cat_idx > #categories then return false end
      local cat = categories[cat_idx]
      local notes = response_data.notes[cat]
      
      if #notes > 0 then
        local target_track_idx = nil
        for i = 1, song.sequencer_track_count do
          if song:track(i).name:match("^Track %d+$") then
            target_track_idx = i
            break
          end
        end
        if not target_track_idx then
          target_track_idx = song.sequencer_track_count + 1
          song:insert_track_at(target_track_idx)
        end
        local track = song:track(target_track_idx)
        local display_name = cat:gsub("_", " "):gsub("^%l", string.upper)
        track.name = "MIDI: " .. display_name
        
        local target_instr_idx = nil
        for i = 1, #song.instruments do
          local iname = song:instrument(i).name
          if iname == "" or iname == "Init" or iname:match("^Instrument %d+$") then
            target_instr_idx = i
            break
          end
        end
        if not target_instr_idx then
          target_instr_idx = #song.instruments + 1
          song:insert_instrument_at(target_instr_idx)
        end
        local instr = song:instrument(target_instr_idx)
        instr.name = "AI: " .. display_name
        
        -- Single-stem appends need to make sure the specific appended instr gets a sample buffer to render on
        if #instr.samples == 0 then instr:insert_sample_at(1) end
        
        table.insert(tracks_to_process, {
          track_idx = target_track_idx,
          instr_idx = target_instr_idx,
          notes_raw = notes,
          notes_processed = {},
          processed_count = 0
        })
      end
      cat_idx = cat_idx + 1
      return true
    end
    
    run_task(create_tracks_async, function()
      update_ai_status("Tracks Created. Indexing notes...")
      current_state = "PROCESS_NOTES"
    end)
    return false
  end

  -- STEP 3: ASYNC NOTE INDEXING
  local function task_index_notes()
    local all_done = true
    for _, t in ipairs(tracks_to_process) do
      if t.processed_count < #t.notes_raw then
        all_done = false
        local start_idx = t.processed_count + 1
        local end_idx = math.min(start_idx + 400, #t.notes_raw)
        
        for i = start_idx, end_idx do
          local n = t.notes_raw[i]
          local start_line = math.floor(n.start * lines_per_sec) + 1
          local end_line = math.floor((n.start + n.duration) * lines_per_sec) + 1
          if end_line <= start_line then end_line = start_line + 1 end
          
          table.insert(t.notes_processed, {
            abs_line = start_line,
            end_line = end_line,
            note = math.max(0, math.min(119, n.note - 12)),
            vol = math.min(127, n.velocity)
          })
        end
        t.processed_count = end_idx
        update_ai_status(string.format("Indexing: %d notes ready...", t.processed_count))
        break -- Process one track slice per tick
      end
    end
    
    if all_done then
      current_state = "EXPAND_SONG"
      return false
    end
    return true
  end

  -- STEP 4: ASYNC SONG EXPANSION
  local function task_expand_song()
    local max_line = 0
    for _, t in ipairs(tracks_to_process) do
      for _, n in ipairs(t.notes_processed) do
        if n.end_line and n.end_line > max_line then 
          max_line = n.end_line 
        elseif n.abs_line > max_line then 
          max_line = n.abs_line 
        end
      end
    end
    
    local total_lines = 0
    for i = 1, #song.sequencer.pattern_sequence do
      total_lines = total_lines + song:pattern(song.sequencer:pattern(i)).number_of_lines
    end

    local function expand_pats()
      if total_lines < (max_line + 64) then
        song.sequencer:insert_new_pattern_at(#song.sequencer.pattern_sequence + 1)
        total_lines = total_lines + song:pattern(song.sequencer:pattern(#song.sequencer.pattern_sequence)).number_of_lines
        update_ai_status("Expanding patterns...")
        return true
      end
      return false
    end
    
    run_task(expand_pats, function()
      update_ai_status("Patterns ready. Building line map...")
      current_state = "BUILD_MAP"
    end)
    return false
  end

  -- STEP 5: ASYNC LINE MAP & FINAL WRITE
  local line_map = {}
  local function task_build_map()
    local total = 0
    local seq_idx = 1
    
    local function index_map_slice()
      if seq_idx > #song.sequencer.pattern_sequence then return false end
      
      -- Do up to 10 patterns per chunk
      for _ = 1, 10 do
        if seq_idx > #song.sequencer.pattern_sequence then return false end
        local pat_len = song:pattern(song.sequencer:pattern(seq_idx)).number_of_lines
        for l = 1, pat_len do
          line_map[total + l] = { s = seq_idx, l = l }
        end
        total = total + pat_len
        seq_idx = seq_idx + 1
      end
      update_ai_status(string.format("Mapping song: %d patterns...", seq_idx))
      return true
    end
    
    run_task(index_map_slice, function()
      update_ai_status("Map ready. Writing MIDI data...")
      current_state = "FINAL_WRITE"
    end)
    return false
  end

  local write_track_idx = 1
  local write_note_idx = 1
  local function task_final_write()
    if write_track_idx > #tracks_to_process then
      update_ai_status("MIDI Import Complete!")
      current_state = "DONE"
      
      local delay_ticks = 0
      local function delayed_close()
        delay_ticks = delay_ticks + 1
        if delay_ticks >= 100 then -- approx 2000ms
          close_ai_status_dialog()
          renoise.tool():remove_timer(delayed_close)
        end
      end
      renoise.tool():add_timer(delayed_close, 20)
      
      return false
    end
    
    local t = tracks_to_process[write_track_idx]
    
    -- Ensure Track has polyphonic columns setup
    local trk = song:track(t.track_idx)
    if trk.visible_note_columns < 8 then
      trk.visible_note_columns = 8
    end
    
    local end_idx = math.min(write_note_idx + 150, #t.notes_processed)
    
    for i = write_note_idx, end_idx do
      local n = t.notes_processed[i]
      local start_pos = line_map[n.abs_line]
      local end_pos = line_map[n.end_line]
      
      -- Distribute notes cyclically across 8 polyphonic columns to prevent immediate cutoffs
      local col_idx = (i % 8) + 1
      
      if start_pos then
        local pattern = song:pattern(song.sequencer:pattern(start_pos.s))
        local col = pattern:track(t.track_idx).lines[start_pos.l]:note_column(col_idx)
        col.note_value = n.note
        col.instrument_value = t.instr_idx - 1
        col.volume_value = n.vol
      end
      
      if end_pos then
        local end_pattern = song:pattern(song.sequencer:pattern(end_pos.s))
        local col = end_pattern:track(t.track_idx).lines[end_pos.l]:note_column(col_idx)
        -- Write note-off (value 120) if column doesn't currently hold a brand new note on the same line
        if col.note_value == 121 then
          col.note_value = 120
        end
      end
    end
    
    write_note_idx = end_idx + 1
    if write_note_idx > #t.notes_processed then
      write_track_idx = write_track_idx + 1
      write_note_idx = 1
    else
      update_ai_status(string.format("Writing track %d: %d%%...", write_track_idx, math.floor((write_note_idx/#t.notes_processed)*100)))
    end
    return true
  end

  -- MAIN STATE MACHINE LOOP
  local main_pipeline_timer = nil
  local function main_pipeline()
    if current_state == "READY" then
      current_state = "CLEANUP"
      run_task(task_cleanup)
    elseif current_state == "QUEUE_DATA" then
      current_state = "PREPARE"
      run_task(task_prepare_data)
    elseif current_state == "PROCESS_NOTES" then
      task_index_notes()
    elseif current_state == "EXPAND_SONG" then
       current_state = "EXPANDING"
       run_task(task_expand_song)
    elseif current_state == "BUILD_MAP" then
       current_state = "MAPPING"
       run_task(task_build_map)
    elseif current_state == "FINAL_WRITE" then
       task_final_write()
    elseif current_state == "DONE" then
       renoise.tool():remove_timer(main_pipeline)
    end
  end

  renoise.tool():add_timer(main_pipeline, 20)

  -- ASYNC VOCAL LOAD (Parallel)
  if response_data.stems and response_data.stems.vocals then
    local local_url = response_data.stems.vocals:gsub("192.168.200.121", "127.0.0.1")
    renoise_http_async(local_url, "GET", nil, false, function()
      local vocal_wav = renoise.tool().bundle_path .. "vocals_async.wav"
      os.rename(renoise.tool().bundle_path .. "http_res.tmp", vocal_wav)
      
      local function load_vocal_to_song()
        local instr = song:insert_instrument_at(2)
        instr.name = "Audio Stem: Vocals"
        instr:insert_sample_at(1)
        instr.samples[1].sample_buffer:load_from(vocal_wav)
        instr.samples[1].autoseek = true
        os.remove(vocal_wav)
        
        local track = song:track(1)
        track.name = "Vocals (Audio)"
        song:pattern(song.sequencer:pattern(1)):track(1).lines[1]:note_column(1).note_value = 48
        song:pattern(song.sequencer:pattern(1)):track(1).lines[1]:note_column(1).instrument_value = 1
      end
      -- Delay vocal load to ensure tracks exist
      renoise.tool():add_timer(load_vocal_to_song, 2000)
    end)
  end
end

--------------------------------------------------------------------------------
-- Polling for Async Tasks
--------------------------------------------------------------------------------

function poll_task_status(task_id, on_success)
  local poll_url = options.server_url.value .. "/task_status/" .. task_id
  
  local is_polling = false
  local function do_poll()
    if is_polling then return end
    is_polling = true
    
    renoise_http_async(poll_url, "GET", nil, false, function(raw_res)
      is_polling = false
      if not raw_res or raw_res == "" then return end
      
      local ok, data = pcall(json.decode, raw_res)
      if not ok or not data then return end
      
      if data.status == "success" then
        renoise.tool():remove_timer(do_poll)
        update_ai_status("Server work complete. Importing to patterns...")
        on_success(data)
      elseif data.status == "error" or (data.error and data.error ~= "") then
        renoise.tool():remove_timer(do_poll)
        close_ai_status_dialog()
        renoise.app():show_error("AI Suite Error: " .. (data.error or "Unknown server error"))
      else
        update_ai_status(data.message or "working on your song...")
      end
    end)
  end
  
  renoise.tool():add_timer(do_poll, 3000)
end

--------------------------------------------------------------------------------
-- UI Related Functions
--------------------------------------------------------------------------------

local function pick_file_and_upload(endpoint_path, status_msg, is_append_only)
  local filepath = renoise.app():prompt_for_filename_to_read({"*.wav", "*.flac", "*.mp3"}, "Select Audio File for AI Analysis")
  if filepath == "" then return end
  
  renoise.app():show_status(status_msg)
  
  renoise_http_async(options.server_url.value .. endpoint_path, "POST", filepath, false, function(raw_response)
    if not raw_response or raw_response == "" then
      renoise.app():show_status("AI Suite: Server Error during processing.")
      return
    end
    
    local ok, response_data = pcall(json.decode, raw_response)
    if not ok or not response_data then
      renoise.app():show_error("AI Suite: Invalid response from server.")
      print("Raw Server Response:", raw_response)
      return
    end
    
    if response_data.status == "pending" and response_data.task_id then
      show_ai_status_dialog("Communicating with GPU Workstation...")
      poll_task_status(response_data.task_id, function(data)
        process_ai_audio_analysis_response(data, is_append_only)
      end)
    elseif response_data.status == "success" then
      show_ai_status_dialog("Importing AI Result...")
      process_ai_audio_analysis_response(response_data, is_append_only)
    else
      renoise.app():show_error("AI Suite: Processing failed " .. (response_data.error or ""))
      print("Raw Server Response:", raw_response)
    end
  end)
end


local function import_single_stem_to_midi()
  pick_file_and_upload("/transcribe", "AI Suite: Quick Appending Single Stem...", true)
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
renoise.tool():add_menu_entry { name = "Main Menu:Tools:AI Integration:Compose Track with AI (Ollama)...", invoke = compose_with_ai }

renoise.tool():add_menu_entry { name = "Main Menu:Tools:AI Integration:Convert Single Stem -> MIDI...", invoke = import_single_stem_to_midi }
renoise.tool():add_menu_entry { name = "Main Menu:Tools:AI Integration:Preferences...", invoke = configure_api_preferences }

-- Context Menus (Right Click)
renoise.tool():add_menu_entry { name = "Pattern Editor:AI Integration:Compose Track with AI (Ollama)...", invoke = compose_with_ai }

renoise.tool():add_menu_entry { name = "Pattern Editor:AI Integration:Convert Single Stem -> MIDI...", invoke = import_single_stem_to_midi }
renoise.tool():add_menu_entry { name = "Sample Editor:AI Integration:Convert Sample -> MIDI...", invoke = import_single_stem_to_midi }

print("AI Suite initialized. Native MIDI generation primed.")
