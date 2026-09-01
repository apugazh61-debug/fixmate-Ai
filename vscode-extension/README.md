# FixMate AI — VS Code Extension

Sub-second real-time Python code diagnostics and 1-click Quick Fixes powered by the FixMate AI local engine.

---

## ⚡ How It Works

1. **On Save:** Whenever you save a `.py` file, the extension sends the buffer to `POST http://127.0.0.1:8000/analyze/inline`.
2. **Native Diagnostics:** Issues (missing imports, syntax errors, undefined typos) appear immediately as squiggly underlines on the exact line.
3. **1-Click Quick Fix:** Click on the yellow lightbulb or press `Ctrl + .` (or `Cmd + .` on Mac) and choose **"🛠️ FixMate: Apply automated fix"** to instantly repair the file.

---

## 🚀 Running in Extension Development Host (F5)

### Step 1: Start the FixMate Backend Service
In your terminal, navigate to the `fixmate_ai` directory and run:
```bash
uvicorn webhook_app:app --port 8000
```
Verify the service is running at `http://127.0.0.1:8000/health`.

### Step 2: Open and Build the Extension
1. Open the `vscode-extension/` directory in VS Code.
2. Install dependencies and compile TypeScript:
   ```bash
   npm install
   npm run compile
   ```

### Step 3: Launch Debugger (F5)
1. Press `F5` (or click **Run -> Start Debugging**).
2. A new **[Extension Development Host]** VS Code window will launch with the FixMate AI extension active.
3. Open or create any Python file (e.g. `test_demo.py`):
   ```python
   def area(r):
       return math.pi * r ** 2
   ```
4. Save the file (`Ctrl + S`).
5. Notice the squiggly underline on line 2 (`math.pi`), click `Ctrl + .`, and apply the Quick Fix!
