-- main.lua
-- Renoise AI Suite
-- Connects to local Python server at localhost:5000

local json = require "json"

local options = renoise.Document.create("ScriptingToolPreferences") {
  server_url = "http://localhost:5000",
  api_key = "my_super_secret_proxmox_key"
}

renoise.tool().preferences = options

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function os_execute_curl(url, method, filepath)
  local cmd = string.format('curl -s -X %s -H "X-API-Key: %s" "%s"', method, options.api_key.value, url)
  if method == "POST" and filepath then
    cmd = string.format('curl -s -X POST -H "X-API-Key: %s" -F "file=@%s" "%s"', options.api_key.value, filepath, url)
  end
  
  -- Run command and read output
  local handle = io.popen(cmd)
  local result = handle:read("*a")
  handle:close()
  return result
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
  
  renoise.app():show_status("AI Suite: Sending audio to AI server...")
  
  -- Call Python Server
  local raw_response = os_execute_curl(options.server_url.value .. "/transcribe", "POST", temp_path)
  
  -- Cleanup temp file early
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
  
  local pattern = song.selected_pattern
  local track_index = song.selected_track_index
  local track = pattern:track(track_index)
  local lines_in_pattern = pattern.number_of_lines
  
  -- Calculate Time to Lines
  -- Lines Per Beat * Beats Per Minute = Lines Per Minute
  -- Lines Per Minute / 60 = Lines Per Second
  local bpm = song.transport.bpm
  local lpb = song.transport.lpb
  local lines_per_sec = (bpm * lpb) / 60.0
  
  -- Notes are assumed to be sorted by start time
  for _, note in ipairs(response_data.notes) do
    -- server returns start in seconds
    local line_index = math.floor(note.start * lines_per_sec) + 1
    
    if line_index <= lines_in_pattern then
      local line = track:line(line_index)
      local note_col = line:note_column(1)
      
      -- Convert MIDI note (0-127) to Renoise Note (0-119, C-4=48)
      -- Renoise: 0 = C-0, 12 = C-1 ... 48 = C-4.
      -- MIDI: 60 = C4.
      -- So Renoise = MIDI - 12
      local renoise_note = math.max(0, math.min(119, note.note - 12))
      
      note_col.note_value = renoise_note
      note_col.instrument_value = song.selected_instrument_index - 1
      note_col.volume_value = math.min(127, note.velocity)
    else
        print("Note out of bounds:", line_index)
    end
  end
  
  renoise.app():show_status("AI Suite: Transcription Done.")
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
  
  local raw_response = os_execute_curl(options.server_url.value .. "/transcribe_full", "POST", temp_path)
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
  
  local pattern = song.selected_pattern
  local lines_in_pattern = pattern.number_of_lines
  local bpm = song.transport.bpm
  local lpb = song.transport.lpb
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

  -- Load stems and create tracks
  local stems_order = {"vocals", "drums", "bass", "other"}
  
  for _, stem_name in ipairs(stems_order) do
    local url = response_data.stems[stem_name]
    if url then
      local stem_temp = os.tmpname() .. ".wav"
      -- Download the file
      local cmd = string.format('curl -s -L "%s" -o "%s"', url, stem_temp)
      os.execute(cmd)
      
      -- Create Instrument
      local instr = song:insert_instrument_at(#song.instruments + 1)
      instr.name = "AI Stem: " .. stem_name
      
      -- Load sample
      local smp = instr.samples[1]
      smp.sample_buffer:load_from(stem_temp)
      os.remove(stem_temp)
      
      -- Create Track and trigger at line 1
      local track = song:insert_track_at(#song.tracks)
      track.name = "Stem: " .. stem_name
      local note_col = pattern:track(song.tracks[#song.tracks]).lines[1]:note_column(1)
      note_col.note_value = 48 -- C-4
      note_col.instrument_value = #song.instruments - 1
    end
  end
  
  -- Create MIDI Tracks for Bass and Melody
  if response_data.notes and response_data.notes.bass then
    local track = song:insert_track_at(#song.tracks)
    track.name = "MIDI: Bass"
    local instr = song:insert_instrument_at(#song.instruments + 1)
    instr.name = "MIDI Synth: Bass"
    write_notes(pattern:track(song.tracks[#song.tracks]), response_data.notes.bass, #song.instruments - 1)
  end
  
  if response_data.notes and response_data.notes.melody then
    local track = song:insert_track_at(#song.tracks)
    track.name = "MIDI: Melody"
    local instr = song:insert_instrument_at(#song.instruments + 1)
    instr.name = "MIDI Synth: Melody"
    write_notes(pattern:track(song.tracks[#song.tracks]), response_data.notes.melody, #song.instruments - 1)
  end

  renoise.app():show_status("AI Suite: Full Transcription Done!")
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
        
        local cmd = string.format("curl -s -X POST -H 'X-API-Key: %s' -H 'Content-Type: application/json' -d '%s' %s/generate_song", options.api_key.value, json_body, options.server_url.value)
        
        local handle = io.popen(cmd)
        local res = handle:read("*a")
        handle:close()
        
        if res and res ~= "" then
            local data = json.decode(res)
            if data and data.status == "success" then
               renoise.app():show_status("AI Suite: Success! Downloading audio...")
               -- Auto-download and load
               local dl_temp = os.tmpname() .. ".wav"
               local dl_cmd = string.format('curl -s -L "%s" -o "%s"', data.file_url, dl_temp)
               os.execute(dl_cmd)
               
               local song = renoise.song()
               local instr = song:insert_instrument_at(song.selected_instrument_index + 1)
               instr.name = "AI: " .. style:sub(1,10)
               
               local smp = instr.samples[1]
               smp.sample_buffer:load_from(dl_temp)
               os.remove(dl_temp)
               
               song.selected_instrument_index = song.selected_instrument_index + 1
               renoise.app():show_status("AI Suite: Audio loaded into new instrument.")
            elseif data and data.error then
               renoise.app():show_error("AI Suite Error: " .. data.error)
            else
               renoise.app():show_status("AI Suite: Info: " .. (data.info or "Unknown error"))
            end
        else 
             renoise.app():show_status("AI Suite: Failed to contact server during generation.")
        end
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
