import os
import zipfile
import xml.etree.ElementTree as ET
import glob
import json
import multiprocessing
from tqdm import tqdm

DATASET_DIR = "/home/juanquy/dev/Renoise AI Plugin/XRNS-DataSet/"
OUTPUT_PATH = "/home/juanquy/dev/Renoise AI Plugin/dataset_full.jsonl"

def process_single_xrns(filepath):
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
                        tracks.append(track.find('Name').text if track.find('Name') is not None else "Track")
                    
                    # 3. Pattern Data
                    patterns_data = []
                    for idx, pat in enumerate(root.findall('.//PatternPool/Patterns/Pattern')):
                        lines_in_pat = pat.find('.//NumberOfLines')
                        num_lines = int(lines_in_pat.text) if lines_in_pat is not None else 64
                        
                        active_lines = []
                        for line in pat.findall('.//Lines/Line'):
                            line_idx = line.get('index')
                            
                            notes = []
                            for note_col in line.findall('.//NoteColumns/NoteColumn'):
                                note = note_col.find('Note')
                                instr = note_col.find('Instrument')
                                if note is not None and note.text != 'OFF':
                                    # Format: Note-Accidental-Octave (Instrument ID)
                                    notes.append(f"{note.text}({instr.text if instr is not None else '?'})")
                                   
                            if notes:
                                active_lines.append(f"L{line_idx}: {', '.join(notes)}")
                                
                        if active_lines:
                            patterns_data.append({
                                "len": num_lines,
                                "events": active_lines
                            })
                    
                    if not patterns_data:
                        return None
                        
                    return {
                        "song": filename,
                        "bpm": bpm,
                        "lpb": lpb,
                        "tracks": tracks,
                        "patterns": patterns_data
                    }
    except Exception as e:
        return {"error": str(e), "file": filename}
    return None

def build_dataset_parallel():
    xrns_files = glob.glob(os.path.join(DATASET_DIR, "*.xrns"))
    print(f"Found {len(xrns_files)} XRNS files to process.")
    
    # Leave one core free so the system doesn't lock up
    num_cores = max(1, multiprocessing.cpu_count() - 1)
    print(f"Starting multiprocessing pool mapping {num_cores} parallel cores...")
    
    success_count = 0
    error_count = 0
    
    with open(OUTPUT_PATH, 'w') as out_f:
        with multiprocessing.Pool(processes=num_cores) as pool:
            # Process files in parallel and stream JSON lines as they finish
            for result in tqdm(pool.imap_unordered(process_single_xrns, xrns_files), total=len(xrns_files)):
                if result:
                    if "error" in result:
                        error_count += 1
                    else:
                        out_f.write(json.dumps(result) + '\n')
                        success_count += 1
                        
    print(f"\nPipeline Finished!")
    print(f"Successfully Tokenized: {success_count} songs")
    print(f"Failed/Corrupted: {error_count} songs")
    print(f"Output saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_dataset_parallel()
