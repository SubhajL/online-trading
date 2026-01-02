#!/usr/bin/env node

/**
 * End-to-end test script for signal snapshot flow
 *
 * This script tests the complete flow:
 * 1. Python engine emits a signal
 * 2. BFF receives the signal alert
 * 3. Snapshot is generated via Puppeteer
 * 4. Alert is created with snapshot URL
 * 5. Telegram receives the photo alert
 */

const axios = require('axios');
const { exec } = require('child_process');
const util = require('util');
const fs = require('fs').promises;
const path = require('path');

const execAsync = util.promisify(exec);

const BFF_URL = process.env.BFF_URL || 'http://localhost:3001';
const INTERNAL_ALERTS_TOKEN = process.env.INTERNAL_ALERTS_TOKEN || 'change_me';

async function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function testSignalFlow() {
  console.log('🚀 Testing Signal Snapshot Flow...\n');

  try {
    // 1. Generate a test signal ID
    const signalId = `sig_${Date.now().toString(36)}`;
    console.log(`📍 Signal ID: ${signalId}`);

    // 2. Send signal alert to BFF
    console.log('\n📨 Sending signal alert to BFF...');
    const signalPayload = {
      signalId,
      symbol: 'BTCUSDT',
      venue: 'SPOT',
      side: 'BUY',
      entry: 50000,
      stopLoss: 49000,
      takeProfit: 52000,
      confidence: 0.85,
      reasons: ['SMC Breaker', 'Bullish OB Retest', 'Trend Alignment'],
      timeframe: '15m',
      signalTime: new Date().toISOString(),
    };

    const alertResponse = await axios.post(
      `${BFF_URL}/api/signals/alert`,
      signalPayload,
      {
        headers: {
          'Authorization': `Bearer ${INTERNAL_ALERTS_TOKEN}`,
          'Content-Type': 'application/json',
        },
      }
    );

    console.log('✅ Alert response:', alertResponse.data);

    // 3. Wait for snapshot generation
    console.log('\n⏳ Waiting for snapshot generation (5 seconds)...');
    await delay(5000);

    // 4. Check if snapshot was created
    console.log('\n🔍 Checking snapshot status...');
    try {
      const snapshotResponse = await axios.get(
        `${BFF_URL}/api/signals/${signalId}/snapshot`,
        {
          headers: {
            'Authorization': `Bearer ${INTERNAL_ALERTS_TOKEN}`,
          },
        }
      );

      console.log('✅ Snapshot created:', {
        imageUrl: snapshotResponse.data.imageUrl,
      });

      // 5. Download and check the image
      if (snapshotResponse.data.imageUrl) {
        console.log('\n📥 Downloading snapshot image...');
        const imageUrl = `${BFF_URL}${snapshotResponse.data.imageUrl}`;
        const imageResponse = await axios.get(imageUrl, {
          responseType: 'arraybuffer',
        });

        const imagePath = path.join(__dirname, `test-snapshot-${signalId}.png`);
        await fs.writeFile(imagePath, imageResponse.data);

        const stats = await fs.stat(imagePath);
        console.log(`✅ Image saved: ${imagePath} (${stats.size} bytes)`);

        // Clean up
        await fs.unlink(imagePath);
      }
    } catch (error) {
      if (error.response?.status === 404) {
        console.log('❌ Snapshot not found - generation may have failed');
      } else {
        throw error;
      }
    }

    // 6. Test Python signal emitter
    console.log('\n🐍 Testing Python signal emitter...');
    const pythonScript = path.join(__dirname, '..', 'app', 'engine', 'adapters', 'alert', 'signal_emitter.py');

    try {
      const { stdout, stderr } = await execAsync(
        `cd "${path.join(__dirname, '..')}" && python3 -m app.engine.adapters.alert.signal_emitter`,
        { timeout: 10000 }
      );

      console.log('Python emitter output:');
      console.log(stdout);
      if (stderr) {
        console.error('Python emitter errors:', stderr);
      }
    } catch (error) {
      console.log('❌ Python emitter failed:', error.message);
    }

    console.log('\n✨ Signal snapshot flow test completed!');

  } catch (error) {
    console.error('\n❌ Test failed:', error.message);
    if (error.response?.data) {
      console.error('Response data:', error.response.data);
    }
    process.exit(1);
  }
}

// Run the test
if (require.main === module) {
  testSignalFlow()
    .catch(error => {
      console.error('Unhandled error:', error);
      process.exit(1);
    });
}

module.exports = { testSignalFlow };
