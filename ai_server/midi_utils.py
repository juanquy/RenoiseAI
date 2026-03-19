import symusic
from midi_composer import midi_to_renoise

def midi_to_renoise_commands(midi_path, target_track_map=None, lpb=4, lines_per_pattern=64):
    """
    Parses a MIDI file using symusic and converts it to Renoise 'set_note' commands.
    target_track_map: dict { midi_track_name_lower: renoise_track_index }
    """
    score = symusic.Score.from_file(midi_path)
    commands = []
    
    # Renoise timing: 1 beat = LPB lines. 
    # MIDI timing: score.ticks_per_quarter
    tpq = score.ticks_per_quarter
    
    for i, track in enumerate(score.tracks):
        # Determine target renoise track
        track_name = track.name.lower() or f"track_{i}"
        r_track_idx = i
        if target_track_map:
            # Try to match track name or index
            r_track_idx = target_track_map.get(track_name, i)

        for note in track.notes:
            # Convert ticks to Renoise lines
            # line = (ticks / ticks_per_quarter) * lpb
            total_line = (note.start / tpq) * lpb
            pattern_idx = int(total_line // lines_per_pattern)
            line_in_pattern = int(total_line % lines_per_pattern)
            
            note_str = midi_to_renoise(note.pitch)
            
            commands.append({
                "type": "set_note",
                "track": r_track_idx,
                "track_name": track_name,
                "pattern": pattern_idx,
                "line": line_in_pattern,
                "note": note_str,
                "velocity": note.velocity,
                "instrument": 0 # Will be overridden by worker
            })
            
            # Note Off
            duration_lines = (note.duration / tpq) * lpb
            off_line_total = total_line + max(1, duration_lines)
            off_pattern = int(off_line_total // lines_per_pattern)
            off_line = int(off_line_total % lines_per_pattern)
            
            commands.append({
                "type": "note_off",
                "track": r_track_idx,
                "track_name": track_name,
                "pattern": off_pattern,
                "line": off_line
            })
            
    return commands
