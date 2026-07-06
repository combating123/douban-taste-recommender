$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PYTHONPATH = Join-Path $here "src"
python -m douban_recommender.web
