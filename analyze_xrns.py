import os
import zipfile
import xml.etree.ElementTree as ET
import glob

DATASET_DIR = "/home/juanquy/dev/Renoise AI Plugin/XRNS-DataSet/"

def explore_xrns_structure(limit=1):
    xrns_files = glob.glob(os.path.join(DATASET_DIR, "*.xrns"))
    print(f"Found {len(xrns_files)} .xrns files in dataset.")
    
    for i in range(min(limit, len(xrns_files))):
        filepath = xrns_files[i]
        filename = os.path.basename(filepath)
        print(f"\n--- Exploring {filename} ---")
        
        try:
            with zipfile.ZipFile(filepath, 'r') as z:
                # Renoise song data is always stored in Song.xml inside the zip
                if 'Song.xml' in z.namelist():
                    with z.open('Song.xml') as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        
                        # Basic Song Data
                        global_data = root.find('GlobalSongData')
                        bpm = global_data.find('BeatsPerMin').text if global_data is not None else "Unknown"
                        lpb = global_data.find('LinesPerBeat').text if global_data is not None else "Unknown"
                        print(f"BPM: {bpm}, LPB: {lpb}")
                        
                        # Tracks breakdown
                        tracks = root.find('.//Tracks')
                        if tracks is not None:
                            sequencer_tracks = tracks.findall('SequencerTrack')
                            print(f"Sequencer Tracks: {len(sequencer_tracks)}")
                            for idx, t in enumerate(sequencer_tracks):
                                name = t.find('Name').text if t.find('Name') is not None else "Unnamed"
                                print(f"  Track {idx}: {name}")
                                
                        # Pattern breakdown
                        patterns = root.find('.//PatternPool/Patterns')
                        if patterns is not None:
                            pattern_list = patterns.findall('Pattern')
                            print(f"Total Patterns: {len(pattern_list)}")
                            
                else:
                    print("No Song.xml found in this archive.")
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == "__main__":
    explore_xrns_structure(3)
