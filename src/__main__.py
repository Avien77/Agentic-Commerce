"""`python -m src` starts the terminal chat (`main()` in src/graph.py, notebook 07);
`python -m src --voice` the voice chat (`main()` in src/voice.py, notebook 09);
`python -m src --ui` the web page with a typed chat (`main()` in src/ui.py, notebook 10), and
`--voice --ui` the voice chat with the web page following along.
Hand-written, like nbexport.py."""

import sys

if "--voice" in sys.argv[1:]:
    from src.voice import main
elif "--ui" in sys.argv[1:]:
    from src.ui import main
else:
    from src.graph import main

sys.exit(main())
