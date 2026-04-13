const { LanguageClient, TransportKind } = require("vscode-languageclient/node");
const path = require("path");
const vscode = require("vscode");

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration("nous");
  const pythonPath = config.get("pythonPath", "python3");
  const parserPath = config.get("parserPath", "/opt/aetherlang_agents/nous");

  const serverModule = path.join(context.extensionPath, "server", "nous_lsp.py");

  const serverOptions = {
    run: {
      command: pythonPath,
      args: [serverModule],
      transport: TransportKind.stdio,
      options: { env: { ...process.env, PYTHONPATH: parserPath } },
    },
    debug: {
      command: pythonPath,
      args: [serverModule],
      transport: TransportKind.stdio,
      options: { env: { ...process.env, PYTHONPATH: parserPath } },
    },
  };

  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "nous" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.nous"),
    },
  };

  client = new LanguageClient("nous-lsp", "NOUS Language Server", serverOptions, clientOptions);
  client.start();

  const compileCmd = vscode.commands.registerCommand("nous.compile", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "nous") {
      vscode.window.showWarningMessage("Open a .nous file first");
      return;
    }
    const file = editor.document.fileName;
    const terminal = vscode.window.createTerminal("NOUS");
    terminal.show();
    terminal.sendText(`cd "${parserPath}" && python3 cli.py compile "${file}"`);
  });

  const runCmd = vscode.commands.registerCommand("nous.run", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "nous") {
      vscode.window.showWarningMessage("Open a .nous file first");
      return;
    }
    const file = editor.document.fileName;
    const terminal = vscode.window.createTerminal("NOUS");
    terminal.show();
    terminal.sendText(`cd "${parserPath}" && python3 cli.py run "${file}"`);
  });

  const deployCmd = vscode.commands.registerCommand("nous.deploy", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "nous") {
      vscode.window.showWarningMessage("Open a .nous file first");
      return;
    }
    const file = editor.document.fileName;
    const terminal = vscode.window.createTerminal("NOUS");
    terminal.show();
    terminal.sendText(`cd "${parserPath}" && python3 cli.py deploy "${file}"`);
  });

  context.subscriptions.push(compileCmd, runCmd, deployCmd);
}

function deactivate() {
  if (client) {
    return client.stop();
  }
}

module.exports = { activate, deactivate };
