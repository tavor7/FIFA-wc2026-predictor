const path = require("path");
require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });

/** Load env from project root, then apply app.json settings. */
module.exports = ({ config }) => config;
