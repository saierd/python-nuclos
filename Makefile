documentation: docco-installed
	@docco documentation.py.md

docco-installed: ; @command -v docco >/dev/null 2>&1 || { echo >&2 "Need docco for building the documentation. Aborting."; exit 1; }

