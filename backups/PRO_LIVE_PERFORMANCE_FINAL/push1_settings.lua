-- push1_settings.lua
-- ViewBuilder dialog for Push 1 tool settings.

local M = {}

local prefs = renoise.Document.create("Push1Settings") {
  midi_in_name       = "Ableton Push",
  midi_out_name      = "Ableton Push",
  auto_connect       = true,
  follow_mode        = true,
  default_root_midi  = 0,
  default_scale_idx  = 1,
  default_base_octave = 3,
  step_advance       = 1
}

function M.prefs() return prefs end

function M.show_dialog(on_apply)
  local vb = renoise.ViewBuilder()
  local content = vb:column {
    margin = 10,
    spacing = 10,
    vb:row {
      vb:text { text = "Root Note:", width = 80 },
      vb:popup {
         items = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"},
         bind = prefs.default_root_midi
      }
    },
    vb:row {
      vb:text { text = "Octave:", width = 80 },
      vb:valuebox { min = 0, max = 8, bind = prefs.default_base_octave }
    },
    vb:row {
      vb:text { text = "Step Advance:", width = 80 },
      vb:valuebox { min = 0, max = 32, bind = prefs.step_advance }
    },
    vb:row {
      vb:text { text = "Follow Mode:", width = 80 },
      vb:checkbox { bind = prefs.follow_mode }
    },
    vb:row {
      vb:text { text = "Auto-Connect:", width = 80 },
      vb:checkbox { bind = prefs.auto_connect }
    },
    vb:button {
      text = "Apply & Close",
      notifier = function()
        if on_apply then on_apply() end
        renoise.app():show_status("Push 1: Settings applied.")
      end
    }
  }

  renoise.app():show_custom_dialog("Push 1 Settings", content)
end

renoise.tool().preferences = prefs

return M
