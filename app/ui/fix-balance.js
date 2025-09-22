const fs = require('fs');
const path = require('path');

// Fix Balance objects in files
const files = [
  './src/context/TradingContext.spec.tsx',
  './src/components/Dashboard/Dashboard.spec.tsx',
  './src/components/trading/AccountBalance.spec.tsx'
];

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');

  // Pattern to match Balance objects missing total property
  // Matches patterns like { asset: 'X', free: N, locked: N, venue: 'Y' }
  content = content.replace(
    /(\{\s*asset:\s*['"][^'"]+['"]\s*,\s*free:\s*[\d.]+\s*,\s*locked:\s*[\d.]+)\s*(,\s*venue:\s*['"][^'"]+['"]\s*(?:,\s*usdValue:\s*[\d.]+\s*)?)\}/g,
    (match, p1, p2) => {
      // Extract free and locked values to calculate total
      const freeMatch = match.match(/free:\s*([\d.]+)/);
      const lockedMatch = match.match(/locked:\s*([\d.]+)/);

      if (freeMatch && lockedMatch) {
        const free = parseFloat(freeMatch[1]);
        const locked = parseFloat(lockedMatch[1]);
        const total = free + locked;

        // Insert total property after locked
        return p1 + `, total: ${total}` + p2 + '}';
      }
      return match;
    }
  );

  fs.writeFileSync(file, content);
  console.log(`Fixed: ${file}`);
});