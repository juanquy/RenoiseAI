import os
import zipfile
import xml.etree.ElementTree as ET
import glob
import json

DATASET_DIR = "/home/juanquy/dev/Renoise AI Plugin/XRNS-DataSet/"
OUTPUT_PATH = "/home/juanquy/dev/Renoise AI Plugin/parsed_xrns_dataset.jsonl"

def parse_xrns_to_llm_json(limit=10):
    xrns_files = glob.glob(os.path.join(DATASET_DIR, "*.xrns"))
    print(f"Parsing {min(limit, len(xrns_files))} files...")
    
    with open(OUTPUT_PATH, 'w') as out_f:
        for i in range(min(limit, len(xrns_files))):
            filepath = xrns_files[i]
            filename = os.path.basename(filepath)
            
            try:
                with zipfile.ZipFile(filepath, 'r') as z:
                    if 'Song.xml' in z.namelist():
                        with z.open('Song.xml') as f:
                            tree = ET.parse(f)
                            root = tree.getroot()
                            
                            # 1. Global Data
                            global_data = root.find('GlobalSongData')
                            bpm = global_data.find('BeatsPerMin').text if global_data is not None else "120"
                            lpb = global_data.find('LinesPerBeat').text if global_data is not None else "4"
                            
                            # 2. Tracks Matrix
                            tracks = []
                            for track in root.findall('.//Tracks/SequencerTrack'):
                                tracks.append({
                                    "name": track.find('Name').text if track.find('Name') is not None else "Track",
                                    "color": track.find('Color').text if track.find('Color') is not None else "",
                                })
                            
                            # 3. Pattern Data (The core sequence)
                            # To save tokens, we only extract patterns that actually have notes
                            patterns_data = []
                            for idx, pat in enumerate(root.findall('.//PatternPool/Patterns/Pattern')):
                                lines_in_pat = pat.find('.//NumberOfLines')
                                num_lines = int(lines_in_pat.text) if lines_in_pat is not None else 64
                                
                                active_lines = []
                                for line in pat.findall('.//Lines/Line'):
                                    line_idx = line.get('index')
                                    
                                    # Parse Note Columns
                                    notes = []
                                    for note_col in line.findall('.//NoteColumns/NoteColumn'):
                                        note = note_col.find('Note')
                                        instr = note_col.find('Instrument')
                                        if note is not None and note.text != 'OFF':
                                           notes.append(f"{note.text} ({instr.text if instr is not None else '?'})")
                                           
                                    if notes:
                                        active_lines.append(f"L{line_idx}: {', '.join(notes)}")
                                        
                                if active_lines:
                                    patterns_data.append({
                                        "id": idx,
                                        "length": num_lines,
                                        "events": active_lines
                                    })
                            
                            # Build the training JSON object
                            song_obj = {
                                "file": filename,
                                "bpm": bpm,
                                "lpb": lpb,
                                "tracks": tracks,
                                "patterns": patterns_data
                            }
                            
                            # Write JSONL line
                            out_f.write(json.dumps(song_obj) + '\n')
                            
            except Exception as e:
                print(f"Error parsing {filename}: {e}")
                
    print(f"Extraction complete. Wrote {OUTPUT_PATH}")

if __name__ == "__main__":
    parse_xrns_to_llm_json(5)
