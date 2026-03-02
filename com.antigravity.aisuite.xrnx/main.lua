-- main.lua
-- Renoise AI Suite
-- Connects to local Python server at localhost:5000

local json = require "json"

local options = renoise.Document.create("ScriptingToolPreferences") {
  server_url = "http://192.168.200.121:5000",
  api_key = "my_super_secret_proxmox_key"
}

renoise.tool().preferences = options

-- Force update stored memory in case Renoise cached the old localhost value
options.server_url.value = "http://192.168.200.121:5000"
options.api_key.value = "my_super_secret_proxmox_key"

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function os_execute_curl_async(url, method, filepath_or_body, is_json_body, callback)
  local temp_res = os.tmpname()
  local temp_err = os.tmpname()
  local temp_done = os.tmpname()
  os.remove(temp_done) -- ensure it doesn't accidentally exist
  
  local cmd = ""
  local temp_req = nil
  
  if method == "POST" and not is_json_body and filepath_or_body then
    cmd = string.format("( curl -sS -X POST -H 'X-API-Key: %s' -F 'file=@%s' '%s' > '%s' 2> '%s' ; touch '%s' ) > /dev/null 2>&1 &", options.api_key.value, filepath_or_body, url, temp_res, temp_err, temp_done)
  elseif method == "POST" and is_json_body and filepath_or_body then
    temp_req = os.tmpname()
    local f = io.open(temp_req, "w")
    if f then
      f:write(filepath_or_body)
      f:close()
    end
    cmd = string.format("( curl -sS -X POST -H 'X-API-Key: %s' -H 'Content-Type: application/json' -d '@%s' '%s' > '%s' 2> '%s' ; touch '%s' ) > /dev/null 2>&1 &", options.api_key.value, temp_req, url, temp_res, temp_err, temp_done)
  else
    cmd = string.format("( curl -sS -X %s -H 'X-API-Key: %s' '%s' > '%s' 2> '%s' ; touch '%s' ) > /dev/null 2>&1 &", method, options.api_key.value, url, temp_res, temp_err, temp_done)
  end
  
  print("Executing cURL command:", cmd)
  os.execute(cmd)
  
  local function poll()
    local f = io.open(temp_done, "r")
    if f then
      f:close()
      renoise.tool():remove_timer(poll)
      
      local res_file = io.open(temp_res, "r")
      local res = ""
      if res_file then
        res = res_file:read("*a")
        res_file:close()
      end
      
      local err_file = io.open(temp_err, "r")
      local err_msg = ""
      if err_file then
        err_msg = err_file:read("*a")
        err_file:close()
      end
      
      if err_msg and err_msg ~= "" then
        print("cURL Error:", err_msg)
      end
      
      os.remove(temp_done)
      os.remove(temp_res)
      os.remove(temp_err)
      if temp_req then os.remove(temp_req) end
      
      callback(res)
    end
  end
  
  -- Check every second
  renoise.tool():add_timer(poll, 1000)
end

--------------------------------------------------------------------------------
-- Features
--------------------------------------------------------------------------------

local function transcribe_sample()
  local song = renoise.song()
  local instrument = song.selected_instrument
  local sample = instrument.samples[instrument.selected_sample_index]
  
  if not sample then
    renoise.app():show_status("AI Suite: No sample selected.")
    return
  end
  
  renoise.app():show_status("AI Suite: Saving temp sample...")
  
  local temp_path = os.tmpname() .. ".wav"
  local success = sample.sample_buffer:save_as(temp_path, "wav")
  
  if not success then
    renoise.app():show_status("AI Suite: Failed to save temp sample.")
    return
  end
  
  renoise.app():show_status("AI Suite: Sending audio to AI server... (This runs in background)")
  
  os_execute_curl_async(options.server_url.value .. "/transcribe", "POST", temp_path, false, function(raw_response)
    os.remove(temp_path)
    
    if not raw_response or raw_response == "" then
      renoise.app():show_status("AI Suite: No response from server. Is it running?")
      return
    end
    
    local response_data = json.decode(raw_response)
    
    if not response_data or not response_data.notes then
      renoise.app():show_status("AI Suite: Invalid response from server.")
      print("Server Response:", raw_response)
      return
    end
    
    renoise.app():show_status("AI Suite: Received " .. #response_data.notes .. " notes. Writing to pattern...")
    
    local async_song = renoise.song()
    local pattern = async_song.selected_pattern
    local track_index = async_song.selected_track_index
    local track = pattern:track(track_index)
    local lines_in_pattern = pattern.number_of_lines
    
    local bpm = async_song.transport.bpm
    local lpb = async_song.transport.lpb
    local lines_per_sec = (bpm * lpb) / 60.0
    
    for _, note in ipairs(response_data.notes) do
      local line_index = math.floor(note.start * lines_per_sec) + 1
      
      if line_index <= lines_in_pattern then
        local line = track:line(line_index)
        local note_col = line:note_column(1)
        local renoise_note = math.max(0, math.min(119, note.note - 12))
        
        note_col.note_value = renoise_note
        note_col.instrument_value = async_song.selected_instrument_index - 1
        note_col.volume_value = math.min(127, note.velocity)
      else
          print("Note out of bounds:", line_index)
      end
    end
    
    renoise.app():show_status("AI Suite: Transcription Done.")
  end)
end


local function process_stems_and_notes_response(response_data)
  local async_song = renoise.song()
  local pattern = async_song.selected_pattern
  local lines_in_pattern = pattern.number_of_lines
  local bpm = async_song.transport.bpm
  local lpb = async_song.transport.lpb
  local lines_per_sec = (bpm * lpb) / 60.0
  
  -- Function to write notes to a track
  local function write_notes(track, notes_array, instr_idx)
    for _, note in ipairs(notes_array) do
      local line_index = math.floor(note.start * lines_per_sec) + 1
      if line_index <= lines_in_pattern then
        local line = track:line(line_index)
        local note_col = line:note_column(1)
        local renoise_note = math.max(0, math.min(119, note.note - 12))
        note_col.note_value = renoise_note
        note_col.instrument_value = instr_idx
        note_col.volume_value = math.min(127, note.velocity)
      end
    end
  end

  -- Load the original mix if generated
  if response_data.stems and response_data.stems.mix then
    local url = response_data.stems.mix
    local dict_temp = os.tmpname() .. ".wav"
    os.execute(string.format('curl -s -L -H "X-API-Key: %s" "%s" -o "%s" > /dev/null 2>&1', options.api_key.value, url, dict_temp))
    
    local instr = async_song:insert_instrument_at(#async_song.instruments + 1)
    instr.name = "AI generated mix"
    if #instr.samples == 0 then instr:insert_sample_at(1) end
    instr.samples[1].sample_buffer:load_from(dict_temp)
    os.remove(dict_temp)
    
    local new_track_idx = async_song.sequencer_track_count + 1
    local track = async_song:insert_track_at(new_track_idx)
    track.name = "AI Mix"
    track.visible_note_columns = 1
    local note_col = pattern:track(new_track_idx).lines[1]:note_column(1)
    note_col.note_value = 48 -- C-4
    note_col.instrument_value = #async_song.instruments - 1
  end

  -- Load stems and create tracks
  local stems_order = {"vocals", "drums", "bass", "other"}
  
  for _, stem_name in ipairs(stems_order) do
    if response_data.stems and response_data.stems[stem_name] then
      local url = response_data.stems[stem_name]
      local stem_temp = os.tmpname() .. ".wav"
      -- Download the file
      local cmd = string.format('curl -s -L -H "X-API-Key: %s" "%s" -o "%s" > /dev/null 2>&1', options.api_key.value, url, stem_temp)
      os.execute(cmd)
      
      -- Create Instrument
      local instr = async_song:insert_instrument_at(#async_song.instruments + 1)
      instr.name = "AI Stem: " .. stem_name
      
      -- Load sample
      if #instr.samples == 0 then instr:insert_sample_at(1) end
      local smp = instr.samples[1]
      smp.sample_buffer:load_from(stem_temp)
      os.remove(stem_temp)
      
      -- Create Track and trigger at line 1
      local new_track_idx = async_song.sequencer_track_count + 1
      local track = async_song:insert_track_at(new_track_idx)
      track.name = "Stem: " .. stem_name
      track.visible_note_columns = 1
      local note_col = pattern:track(new_track_idx).lines[1]:note_column(1)
      note_col.note_value = 48 -- C-4
      note_col.instrument_value = #async_song.instruments - 1
    end
  end
  
  -- Create MIDI Tracks for Bass and Melody
  if response_data.notes and response_data.notes.bass then
    local new_track_idx = async_song.sequencer_track_count + 1
    local track = async_song:insert_track_at(new_track_idx)
    track.name = "MIDI: Bass"
    track.visible_note_columns = 1
    local instr = async_song:insert_instrument_at(#async_song.instruments + 1)
    instr.name = "MIDI Synth: Bass"
    write_notes(pattern:track(new_track_idx), response_data.notes.bass, #async_song.instruments - 1)
  end
  
  if response_data.notes and response_data.notes.melody then
    local new_track_idx = async_song.sequencer_track_count + 1
    local track = async_song:insert_track_at(new_track_idx)
    track.name = "MIDI: Melody"
    track.visible_note_columns = 1
    local instr = async_song:insert_instrument_at(#async_song.instruments + 1)
    instr.name = "MIDI Synth: Melody"
    write_notes(pattern:track(new_track_idx), response_data.notes.melody, #async_song.instruments - 1)
  end
end

local function transcribe_full_song()
  local song = renoise.song()
  local instrument = song.selected_instrument
  local sample = instrument.samples[instrument.selected_sample_index]
  
  if not sample then
    renoise.app():show_status("AI Suite: No sample selected for Full Transcription.")
    return
  end
  
  renoise.app():show_status("AI Suite: Saving temp sample...")
  local temp_path = os.tmpname() .. ".wav"
  local success = sample.sample_buffer:save_as(temp_path, "wav")
  
  if not success then return end
  
  renoise.app():show_status("AI Suite: Sending song to AI Demucs+BasicPitch (this will take minutes!)...")
  
  os_execute_curl_async(options.server_url.value .. "/transcribe_full", "POST", temp_path, false, function(raw_response)
    os.remove(temp_path)
    
    if not raw_response or raw_response == "" then
      renoise.app():show_status("AI Suite: Server Error during processing.")
      return
    end
    
    local response_data = json.decode(raw_response)
    if not response_data or response_data.status ~= "success" then
      renoise.app():show_status("AI Suite: Processing failed.")
      return
    end
    
    renoise.app():show_status("AI Suite: Processing complete! Downloading stems and writing tracks...")
    
    process_stems_and_notes_response(response_data)

    renoise.app():show_status("AI Suite: Full Transcription Done!")
  end)
end

local function generate_song_dialog()
  local view = renoise.app().window
  local vb = renoise.ViewBuilder()
  
  local dialog_content = vb:column {
    margin = 10,
    spacing = 5,
    vb:text { text = "Style/Genre:" },
    vb:textfield { id = "style_text", width = 300, text = "Cyberpunk Techno" },
    vb:text { text = "Topic/Prompt:" },
    vb:textfield { id = "prompt_text", width = 300, text = "A dark rolling bassline" },
    vb:text { text = "Lyrics (Requires External API Config in Server):" },
    vb:multiline_textfield { id = "lyrics_text", width = 300, height = 60, text = "" },
    vb:row {
      vb:checkbox { id = "instrumental_check", value = true },
      vb:text { text = "Instrumental Only (Uses Local MusicGen AI)" }
    },
    vb:space { height = 5 },
    vb:button {
      text = "Generate Song",
      width = 300,
      notifier = function()
        local prompt = vb.views.prompt_text.text
        local style = vb.views.style_text.text
        local lyrics = vb.views.lyrics_text.text
        local instrumental = vb.views.instrumental_check.value
        
        renoise.app():show_status("AI Suite: Generating song... (This may take 30+ seconds)")
        
        -- Safe string escape for simplest json construction
        local function escape_str(s) return s:gsub('"', '\\"'):gsub('\n', '\\n') end
        
        local json_body = string.format(
          '{"prompt": "%s", "style": "%s", "lyrics": "%s", "instrumental": %s, "duration": 8}', 
          escape_str(prompt), escape_str(style), escape_str(lyrics), tostring(instrumental)
        )
        
        os_execute_curl_async(options.server_url.value .. "/generate_song", "POST", json_body, true, function(res)
          if res and res ~= "" then
              
              local ok, data = pcall(json.decode, res)
              
              if not ok then
                 renoise.app():show_error("AI Suite Error: Server returned invalid JSON. Please check Renoise scripting terminal for details.")
                 print("JSON Decode Error: ", data)
                 print("Raw Response Fragment: ", res:sub(1, 200))
                 return
              end
              
              if data and data.status == "success" then
                 renoise.app():show_status("AI Suite: Success! Downloading audio and plotting tracks...")
                 
                 process_stems_and_notes_response(data)
                 
                 renoise.app():show_status("AI Suite: Multi-Track Generation Complete!")
              elseif data and data.error then
                 renoise.app():show_error("AI Suite Error: " .. data.error)
              else
                 renoise.app():show_status("AI Suite: Info: " .. (data.info or "Unknown error"))
              end
          else 
               renoise.app():show_status("AI Suite: Failed to contact server during generation.")
          end
        end)
      end
    }
  }
  
  renoise.app():show_custom_dialog("AI Song Generator", dialog_content)
end

local function open_preferences_dialog()
  local view = renoise.app().window
  local vb = renoise.ViewBuilder()
  
  local dialog_content = vb:column {
    margin = 10,
    spacing = 5,
    vb:text { text = "AI Server URL:" },
    vb:textfield { id = "server_url", width = 300, bind = options.server_url },
    vb:text { text = "API Key:" },
    vb:textfield { id = "api_key", width = 300, bind = options.api_key },
    vb:space { height = 10 },
    vb:text { text = "Changes are saved automatically." }
  }
  
  renoise.app():show_custom_dialog("AI Suite Preferences", dialog_content)
end

--------------------------------------------------------------------------------
-- Menu Registration
--------------------------------------------------------------------------------

renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Transcribe Selected Sample",
  invoke = transcribe_sample
}

renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Transcribe Full Song (Demucs)",
  invoke = transcribe_full_song
}

renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Generate Song...",
  invoke = generate_song_dialog
}

renoise.tool():add_menu_entry {
  name = "Pattern Editor:AI Integration:Preferences...",
  invoke = open_preferences_dialog
}
