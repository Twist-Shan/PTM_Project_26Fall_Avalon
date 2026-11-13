# Build the report (PowerShell, from this folder):  .\build.ps1
# Needs TeX Live (XeLaTeX, BibTeX). Figures and tables are already in figures/ and tables/;
# regenerate them with figures/make_figures.py, figures/make_overview_drawio.py and tables/make_tables.py.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
xelatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null
bibtex main | Out-Null
xelatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null
xelatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null
Write-Output 'Built main.pdf'
