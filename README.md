# INC-Core

Discord management bot for Incorporated.

## Run locally

```powershell
cd "C:\Users\Admin\Downloads\INC-Core"
pip install -r requirements.txt
$env:DISCORD_TOKEN = "YOUR_NEW_REGENERATED_TOKEN"
python .\INC-Core.py
```

Keep the token in an environment variable. Do not put it in this folder or commit it to GitHub.

## Cloud deployment

Upload this folder to a private repository or cloud service. Set `DISCORD_TOKEN` as a secret environment variable and use this start command:

```text
python INC-Core.py
```
