"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
function activate(context) {
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('fixmate');
    context.subscriptions.push(diagnosticCollection);
    const latestFixes = new Map();
    async function analyzeDocument(document) {
        if (document.languageId !== 'python') {
            return;
        }
        const config = vscode.workspace.getConfiguration('fixmate');
        const serverUrl = config.get('serverUrl', 'http://127.0.0.1:8000');
        try {
            const response = await fetch(`${serverUrl}/analyze/inline`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    code: document.getText(),
                    file_path: document.fileName,
                }),
            });
            if (!response.ok) {
                return;
            }
            const data = (await response.json());
            diagnosticCollection.delete(document.uri);
            if (!data.issues || data.issues.length === 0) {
                latestFixes.delete(document.uri.toString());
                return;
            }
            const diagnostics = [];
            for (const issue of data.issues) {
                const lineIndex = Math.max(0, (issue.line || 1) - 1);
                const safeLine = Math.min(lineIndex, Math.max(0, document.lineCount - 1));
                const lineText = safeLine < document.lineCount ? document.lineAt(safeLine).text : '';
                const range = new vscode.Range(safeLine, 0, safeLine, Math.max(1, lineText.length));
                const diagnostic = new vscode.Diagnostic(range, `FixMate: ${issue.message}`, vscode.DiagnosticSeverity.Error);
                diagnostic.source = 'FixMate AI';
                diagnostic.code = issue.error_type;
                diagnostics.push(diagnostic);
            }
            diagnosticCollection.set(document.uri, diagnostics);
            latestFixes.set(document.uri.toString(), {
                fixedCode: data.fixed_code,
                explanation: data.explanation,
                issues: data.issues,
            });
        }
        catch {
            // Local service unreachable — fails silently without blocking IDE
        }
    }
    // Trigger analysis on save and open
    context.subscriptions.push(vscode.workspace.onDidSaveTextDocument((doc) => {
        const config = vscode.workspace.getConfiguration('fixmate');
        if (config.get('analyzeOnSave', true)) {
            analyzeDocument(doc);
        }
    }));
    context.subscriptions.push(vscode.workspace.onDidOpenTextDocument((doc) => {
        analyzeDocument(doc);
    }));
    // Register Quick Fix CodeAction Provider
    context.subscriptions.push(vscode.languages.registerCodeActionsProvider({ language: 'python', scheme: 'file' }, {
        provideCodeActions(document, range, context) {
            const hasFixMateDiag = context.diagnostics.some((d) => d.source === 'FixMate AI');
            if (!hasFixMateDiag) {
                return [];
            }
            const fixData = latestFixes.get(document.uri.toString());
            if (!fixData || !fixData.fixedCode) {
                return [];
            }
            const action = new vscode.CodeAction(`🛠️ FixMate: Apply automated fix (${fixData.explanation})`, vscode.CodeActionKind.QuickFix);
            action.isPreferred = true;
            action.edit = new vscode.WorkspaceEdit();
            const fullRange = new vscode.Range(0, 0, document.lineCount, document.lineAt(Math.max(0, document.lineCount - 1)).text.length);
            action.edit.replace(document.uri, fullRange, fixData.fixedCode);
            return [action];
        },
    }, {
        providedCodeActionKinds: [vscode.CodeActionKind.QuickFix],
    }));
    // Manual command
    context.subscriptions.push(vscode.commands.registerCommand('fixmate.analyzeCurrentFile', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            analyzeDocument(editor.document);
            vscode.window.showInformationMessage('FixMate AI: Analysis complete.');
        }
    }));
}
function deactivate() { }
//# sourceMappingURL=extension.js.map