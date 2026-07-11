$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PYTHONPATH = Join-Path $here "src"
# V3 is the default; set CINESCOPE_UI_VERSION=legacy before launch only to roll back.
python -m douban_recommender.web
