@echo off
cd /d C:\Users\User\Desktop\Github\chase-ai-habitat
git add .
set /p MSG="Commit message: "
git commit -m "%MSG%"
git push
echo Done.
pause