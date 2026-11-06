
// --- vazamento injetado (calibração): 40 MB/h = 11111 bytes/s, retidos e tocados (RSS real) ---
const __leak = [];
setInterval(() => { __leak.push(Buffer.alloc(11111, 1)); }, 1000).unref();
// ---------------------------------------------------------------------------------------------
// Main entry point for the Credit Card Phone Association Service
const express = require('express');
const dotenv = require('dotenv');
const { initDatabase } = require('./db/init');

// Import routes
const cardRoutes = require('./routes/cardRoutes');
const errorHandler = require('./middleware/errorHandler');

// Load environment variables
dotenv.config();

// Initialize the app
const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());

// Initialize database
initDatabase();

// Routes
app.use('/', cardRoutes);

// Error handling middleware
app.use(errorHandler);

// Start the server
app.listen(PORT, () => {
  console.log(`Credit Card Phone Association Service running on http://localhost:${PORT}`);
});