#!/usr/bin/env python3
"""
MIDI to Scratch Converter - GUI Version
Easy drag-and-drop interface for converting MIDI files
"""

try:
    import mido
except ImportError:
    print("ERROR: mido library not found!")
    print("Please install it with: pip install mido")
    import sys
    sys.exit(1)

from collections import defaultdict
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os

# Map General MIDI instrument numbers (0-127) to Scratch instruments (1-21)
def gm_to_scratch_instrument(gm_program):
    """Convert General MIDI program number to Scratch instrument (1-21)"""
    instrument_map = {
        range(0, 2): 1,    range(2, 8): 2,    range(8, 9): 16,
        range(9, 11): 17,  range(11, 16): 19, range(16, 24): 3,
        range(24, 28): 4,  range(28, 32): 5,  range(32, 40): 6,
        range(40, 44): 8,  range(44, 48): 7,  range(48, 52): 8,
        range(52, 56): 15, range(56, 64): 9,  range(64, 68): 11,
        range(68, 72): 10, range(72, 74): 12, range(74, 80): 13,
        range(80, 88): 20, range(88, 96): 21, range(96, 104): 21,
        range(104, 108): 13, range(108, 112): 4, range(112, 116): 18,
        range(116, 120): 19, range(120, 128): 21,
    }
    
    for program_range, scratch_inst in instrument_map.items():
        if gm_program in program_range:
            return scratch_inst
    return 1


def round_to_musical_beat(beat_value):
    """Round a beat value to common musical note durations"""
    if beat_value < 0.027:
        return 0.03125  # 128th note
    elif beat_value < 0.035:
        return 0.04     # triplet 64th note
    elif beat_value < 0.045:
        return 0.05     # dotted 64th note
    elif beat_value < 0.0615:
        return 0.0625   # 64th note
    elif beat_value < 0.0825:
        return 0.0833  # triplet 32th note
    elif beat_value < 0.05:
        return 0.1      # dotted 32th note
    elif beat_value < 0.1:
        return 0.125   # 32th note
    elif beat_value < 0.15:
        return 0.166  # triplet 16th note
    elif beat_value < 0.2:
        return 0.25   # 16th note
    elif beat_value < 0.3:
        return 0.33   # triplet 8th note
    elif beat_value < 0.4:
        return 0.5    # 8th note
    elif beat_value < 0.6:
        return 0.75   # 8th note + 16th note
    elif beat_value < 0.8:
        return 1      # quarter note
    elif beat_value < 1.3:
        return 1.5    # dotted quarter
    elif beat_value < 2.5:
        return 2      # half note
    elif beat_value < 3.5:
        return 3      # dotted half
    elif beat_value < 4.5:
        return 4      # whole note
    elif beat_value < 6.5:
        return 6      # dotted whole note
    elif beat_value < 7.5:
        return 7      # triplet whole note
    elif beat_value < 8.5:   
        return 8      # double whole note
    elif beat_value < 10.5:
        return 10     # dotted double whole note
    elif beat_value < 11.5:
        return 11     # triplet double whole note
    elif beat_value < 12.5:
        return 12     # triple whole note
    elif beat_value < 14.5:
        return 14     # dotted triple whole note
    elif beat_value < 15.5:
        return 15     # triplet triple whole note
    elif beat_value < 16.5:
        return 16     # quadruple whole note 
    else:
        return round(beat_value, 2)  # Keep 2 decimal places for longer notes


def midi_to_scratch(midi_file, output_file, progress_callback=None):
    """Convert MIDI file to Scratch-compatible format"""
    
    try:
        mid = mido.MidiFile(midi_file)
    except Exception as e:
        return False, f"Error reading MIDI file: {e}"
    
    ticks_per_beat = mid.ticks_per_beat
    events = []
    current_tempo = 500000
    tempo_changes = {0: current_tempo}
    
    # Process all tracks
    for track_num, track in enumerate(mid.tracks):
        absolute_time = 0
        current_program = 0
        
        for msg in track:
            absolute_time += msg.time
            
            if msg.type == 'note_on' and msg.velocity > 0:
                events.append((absolute_time, 'note_on', {
                    'note': msg.note,
                    'velocity': msg.velocity,
                    'channel': msg.channel,
                    'program': current_program
                }))
            
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                events.append((absolute_time, 'note_off', {
                    'note': msg.note,
                    'channel': msg.channel
                }))
            
            elif msg.type == 'program_change':
                current_program = msg.program
            
            elif msg.type == 'set_tempo':
                current_tempo = msg.tempo
                tempo_changes[absolute_time] = current_tempo
    
    events.sort(key=lambda x: x[0])
    
    if not events:
        return False, "No note events found in MIDI file!"
    
    output_lines = []
    
    # Get initial instrument
    first_instrument = 1
    for time, event_type, data in events:
        if event_type == 'note_on':
            first_instrument = gm_to_scratch_instrument(data['program'])
            break
    
    output_lines.append(f"Instr: {first_instrument}")
    
    # Get initial tempo
    initial_tempo = tempo_changes.get(0, 500000)
    bpm = (60000000 / initial_tempo)
    output_lines.append(f"BPM: {bpm}")
    
    note_end_times = {}
    
    for time, event_type, data in events:
        if event_type == 'note_off':
            key = (data['channel'], data['note'])
            note_end_times[key] = time
    
    # Group notes that are very close together into chords
    tolerance = ticks_per_beat / 32
    grouped_events = []
    processed_times = set()
    
    total_events = len(events)
    for idx, (time, event_type, data) in enumerate(events):
        if progress_callback and idx % 100 == 0:
            progress_callback(idx / total_events * 100)
        
        if event_type != 'note_on':
            continue
        if time in processed_times:
            continue
            
        chord_notes = []
        chord_instrument = gm_to_scratch_instrument(data['program'])
        
        for other_time, other_type, other_data in events:
            if other_type == 'note_on' and abs(other_time - time) <= tolerance:
                chord_notes.append(other_data['note'])
                processed_times.add(other_time)
        
        grouped_events.append((time, 'chord', {
            'notes': chord_notes,
            'program': data['program']
        }))
    
    for time, tempo in tempo_changes.items():
        if time > 0:
            grouped_events.append((time, 'tempo', {'tempo': tempo}))
    
    grouped_events.sort(key=lambda x: x[0])
    
    previous_time = 0
    current_bpm = bpm
    last_instrument = first_instrument
    
    for time_point, event_type, data in grouped_events:
        if event_type == 'tempo':
            new_tempo = data['tempo']
            new_bpm = (60000000 / new_tempo)
            if new_bpm != current_bpm:
                output_lines.append(f"BPM: {new_bpm}")
                current_bpm = new_bpm
            continue
        
        if event_type == 'chord':
            notes_at_time = data['notes']
            instrument_at_time = gm_to_scratch_instrument(data['program'])
            
            if instrument_at_time != last_instrument:
                output_lines.append(f"Instr: {instrument_at_time}")
                last_instrument = instrument_at_time
            
            if time_point > previous_time:
                rest_ticks = time_point - previous_time
                rest_beats = rest_ticks / ticks_per_beat
                if rest_beats >= 0.03125:
                    rest_beats = round_to_musical_beat(rest_beats)
                    output_lines.append(f"Rest: {rest_beats}")
            
            output_lines.append(f"Note: {'~'.join(map(str, sorted(notes_at_time)))}")
            previous_time = time_point
    
    try:
        with open(output_file, 'w') as f:
            f.write('\n'.join(output_lines))
        return True, f"Successfully converted!\nOutput: {output_file}\nTotal lines: {len(output_lines)}"
    except Exception as e:
        return False, f"Error writing output file: {e}"


class MidiConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MIDI to Scratch Converter")
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        # Title
        title = tk.Label(root, text="MIDI to Scratch Converter", font=("Arial", 16, "bold"))
        title.pack(pady=20)
        
        # Instructions
        instructions = tk.Label(root, text="Select a MIDI file to convert for Scratch", font=("Arial", 10))
        instructions.pack(pady=5)
        
        # File selection frame
        file_frame = tk.Frame(root)
        file_frame.pack(pady=20)
        
        self.file_label = tk.Label(file_frame, text="No file selected", width=40, anchor="w", relief="sunken")
        self.file_label.pack(side=tk.LEFT, padx=5)
        
        browse_btn = tk.Button(file_frame, text="Browse...", command=self.browse_file)
        browse_btn.pack(side=tk.LEFT)
        
        # Convert button
        self.convert_btn = tk.Button(root, text="Convert to Scratch Format", command=self.convert, 
                                     state=tk.DISABLED, font=("Arial", 12), bg="#4CAF50", fg="white", 
                                     padx=20, pady=10)
        self.convert_btn.pack(pady=20)
        
        # Progress bar
        self.progress = ttk.Progressbar(root, length=400, mode='determinate')
        self.progress.pack(pady=10)
        
        # Status label
        self.status_label = tk.Label(root, text="", font=("Arial", 9))
        self.status_label.pack(pady=5)
        
        self.midi_file = None
    
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select MIDI file",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")]
        )
        
        if filename:
            self.midi_file = filename
            self.file_label.config(text=os.path.basename(filename))
            self.convert_btn.config(state=tk.NORMAL)
            self.status_label.config(text="")
    
    def update_progress(self, value):
        self.progress['value'] = value
        self.root.update_idletasks()
    
    def convert(self):
        if not self.midi_file:
            return
        
        # Generate output filename
        output_file = os.path.splitext(self.midi_file)[0] + "_scratch.txt"
        
        self.convert_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Converting...")
        self.progress['value'] = 0
        
        success, message = midi_to_scratch(self.midi_file, output_file, self.update_progress)
        
        self.progress['value'] = 100
        
        if success:
            messagebox.showinfo("Success!", message)
            self.status_label.config(text="Conversion complete!", fg="green")
        else:
            messagebox.showerror("Error", message)
            self.status_label.config(text="Conversion failed!", fg="red")
        
        self.convert_btn.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    app = MidiConverterGUI(root)
    root.mainloop()
