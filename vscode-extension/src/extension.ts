import * as vscode from 'vscode';

interface FixMateIssue {
    error_type: string;
    line: number | null;
    message: string;
    detail: string;
    confidence: number;
}

interface FixMateResponse {
    verified: boolean;
    fixed_code: string;
    explanation: string;
    attempts: number;
    source: string;
    issues: FixMateIssue[];
}

interface StoredFix {
    fixedCode: string;
    explanation: string;
    issues: FixMateIssue[];
}

export function activate(context: vscode.ExtensionContext) {
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('fixmate');
    context.subscriptions.push(diagnosticCollection);

    const latestFixes = new Map<string, StoredFix>();

    async function analyzeDocument(document: vscode.TextDocument): Promise<void> {
        if (document.languageId !== 'python') {
            return;
        }

        const config = vscode.workspace.getConfiguration('fixmate');
        const serverUrl = config.get<string>('serverUrl', 'http://127.0.0.1:8000');

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

            const data = (await response.json()) as FixMateResponse;
            diagnosticCollection.delete(document.uri);

            if (!data.issues || data.issues.length === 0) {
                latestFixes.delete(document.uri.toString());
                return;
            }

            const diagnostics: vscode.Diagnostic[] = [];
            for (const issue of data.issues) {
                const lineIndex = Math.max(0, (issue.line || 1) - 1);
                const safeLine = Math.min(lineIndex, Math.max(0, document.lineCount - 1));
                const lineText = safeLine < document.lineCount ? document.lineAt(safeLine).text : '';
                const range = new vscode.Range(
                    safeLine,
                    0,
                    safeLine,
                    Math.max(1, lineText.length)
                );

                const diagnostic = new vscode.Diagnostic(
                    range,
                    `FixMate: ${issue.message}`,
                    vscode.DiagnosticSeverity.Error
                );
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
        } catch {
            // Local service unreachable — fails silently without blocking IDE
        }
    }

    // Trigger analysis on save and open
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument((doc) => {
            const config = vscode.workspace.getConfiguration('fixmate');
            if (config.get<boolean>('analyzeOnSave', true)) {
                analyzeDocument(doc);
            }
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument((doc) => {
            analyzeDocument(doc);
        })
    );

    // Register Quick Fix CodeAction Provider
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            { language: 'python', scheme: 'file' },
            {
                provideCodeActions(document: vscode.TextDocument, range: vscode.Range | vscode.Selection, context: vscode.CodeActionContext): vscode.CodeAction[] {
                    const hasFixMateDiag = context.diagnostics.some((d) => d.source === 'FixMate AI');
                    if (!hasFixMateDiag) {
                        return [];
                    }

                    const fixData = latestFixes.get(document.uri.toString());
                    if (!fixData || !fixData.fixedCode) {
                        return [];
                    }

                    const action = new vscode.CodeAction(
                        `🛠️ FixMate: Apply automated fix (${fixData.explanation})`,
                        vscode.CodeActionKind.QuickFix
                    );
                    action.isPreferred = true;
                    action.edit = new vscode.WorkspaceEdit();

                    const fullRange = new vscode.Range(
                        0,
                        0,
                        document.lineCount,
                        document.lineAt(Math.max(0, document.lineCount - 1)).text.length
                    );
                    action.edit.replace(document.uri, fullRange, fixData.fixedCode);

                    return [action];
                },
            },
            {
                providedCodeActionKinds: [vscode.CodeActionKind.QuickFix],
            }
        )
    );

    // Manual command
    context.subscriptions.push(
        vscode.commands.registerCommand('fixmate.analyzeCurrentFile', () => {
            const editor = vscode.window.activeTextEditor;
            if (editor) {
                analyzeDocument(editor.document);
                vscode.window.showInformationMessage('FixMate AI: Analysis complete.');
            }
        })
    );
}

export function deactivate() {}
