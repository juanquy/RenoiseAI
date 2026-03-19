import zipfile
import xml.etree.ElementTree as ET
import os
import sys

def parse_renoise_pattern(xrns_path):
    """
    Extracts Song.xml from a Renoise .xrns file and converts
    pattern data into a linear token stream for LLM training.
    """
    print(f"Opening {xrns_path}...")
    try:
        with zipfile.ZipFile(xrns_path, 'r') as z:
            with z.open('Song.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                # Locate the Sequencing Patterns
                patterns = root.find('.//Patterns')
                if patterns is None:
                    print("No patterns found.")
                    return
                
                print("\n--- BEGIN TOKEN STREAM ---")
                
                # Iterate through Patterns
                for pat_idx, pattern in enumerate(patterns.findall('Pattern')):
                    tracks = pattern.find('Tracks')
                    if tracks is None: continue
                    
                    # Iterate through Tracks in the Pattern
                    for trk_idx, track in enumerate(tracks.findall('PatternTrack')):
                        lines = track.find('Lines')
                        if lines is None: continue
                        
                        # Iterate through Lines (Time) in the Track
                        for line in lines.findall('Line'):
                            line_idx = line.get('index')
                            
                            note_columns = line.find('NoteColumns')
                            if note_columns is not None:
                                for col_idx, nc in enumerate(note_columns.findall('NoteColumn')):
                                    note = nc.findtext('Note', '---')
                                    instr = nc.findtext('Instrument', '..')
                                    vol = nc.findtext('Volume', '..')
                                    
                                    # Create the Sequence Token
                                    if note != '---' or instr != '..':
                                        token = f"<pat:{pat_idx}><trk:{trk_idx}><L:{line_idx}><N:{note}><I:{instr}><V:{vol}>"
                                        print(token)
                                        
                print("--- END TOKEN STREAM ---\n")
                
    except Exception as e:
        print(f"Error parsing {xrns_path}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python v2_data_extractor.py <song.xrns> or <directory>")
        sys.exit(1)
        
    path = sys.argv[1]
    if os.path.isfile(path):
        parse_renoise_pattern(path)
    else:
        # Batch mode
        import glob
        files = glob.glob(os.path.join(path, "**/*.xrns"), recursive=True)
        print(f"Found {len(files)} files in {path}")
        for i, f in enumerate(files[:10]): # Preview first 10
            print(f"\n--- File {i+1}: {os.path.basename(f)} ---")
            parse_renoise_pattern(f)
