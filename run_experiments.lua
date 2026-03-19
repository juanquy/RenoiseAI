print("==== Renoise Experiment Script Executing ====")
renoise.app():show_status("Running AI Composer Experiments Headless...")

-- 1. Get references to our plugin functions if they are global
-- We can also just make the API calls directly since we know how to use them
local json = require("json") -- Requires our tool's json or a global one...

-- Actually, it might be safer to execute a curl script from outside and just have this script parse the resulting JSON and build the song.
-- Even better, wait, this script runs *outside* of our tool's scope so `json` might not be available unless we load it.
-- Let's just create a quick .xrns using Python, it's safer.
