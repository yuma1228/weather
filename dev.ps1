# server(8000) / client(8001) / frontend(5173) をまとめて別ウィンドウで起動
$root = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; py -m uvicorn server:app --host localhost --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; py -m uvicorn client:app --host localhost --port 8001"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Output "3 windows started (server / client / frontend). Close each window or Ctrl+C to stop."
