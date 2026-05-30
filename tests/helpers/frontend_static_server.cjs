const fs = require("fs");
const http = require("http");
const path = require("path");

function contentTypeFor(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".js")) return "application/javascript; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".svg")) return "image/svg+xml";
  if (filePath.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

async function startFrontendStaticServer(frontendRoot) {
  const server = http.createServer((req, res) => {
    const urlPath = (req.url || "/").split("?")[0];
    let relativePath = decodeURIComponent(urlPath);
    if (relativePath === "/") relativePath = "/index.html";
    if (relativePath === "/admin") relativePath = "/admin/index.html";
    if (relativePath === "/admin/") relativePath = "/admin/index.html";

    const fullPath = path.resolve(frontendRoot, `.${relativePath}`);
    const normalizedRoot = path.resolve(frontendRoot);
    const relativeToRoot = path.relative(normalizedRoot, fullPath);
    if (relativeToRoot.startsWith("..") || path.isAbsolute(relativeToRoot)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    fs.readFile(fullPath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }
      res.writeHead(200, { "Content-Type": contentTypeFor(fullPath) });
      res.end(data);
    });
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const address = server.address();
  return { server, baseUrl: `http://127.0.0.1:${address.port}` };
}

module.exports = { startFrontendStaticServer };
