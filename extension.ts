import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("nous.lsp");
  const enabled = config.get<boolean>("enabled", true);
  if (!enabled) {
    return;
  }

  const pythonPath = config.get<string>("pythonPath", "python3");
  let serverPath = config.get<string>("serverPath", "");
  if (!serverPath) {
    serverPath = path.join(context.extensionPath, "server", "nous_lsp.py");
  }

  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: [serverPath],
    options: { cwd: path.dirname(serverPath) },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "nous" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.nous"),
    },
  };

  client = new LanguageClient(
    "nous-lsp",
    "NOUS Language Server",
    serverOptions,
    clientOptions
  );

  client.start();
  context.subscriptions.push({
    dispose: () => {
      if (client) {
        client.stop();
      }
    },
  });
}

export function deactivate(): Thenable<void> | undefined {
  if (client) {
    return client.stop();
  }
  return undefined;
}
