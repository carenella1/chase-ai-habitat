@echo off
set /p msg="Commit message: "
git add -A
git add data/journal_archive_*.jsonl 2>nul
git add data/knowledge_synthesis.json 2>nul
git add data/research_sessions.jsonl 2>nul
git commit -m "%msg%"
git push
echo.
echo Pushed successfully.
pause