'use strict';
// Writes the server address into a signed APK without breaking its v2/v3 signature.
//
// The APK Signing Block (between the ZIP entries and the central directory) may contain extra
// ID-value pairs that the signature does not cover. We add one with our server URL and shift the
// central-directory offset in the End-Of-Central-Directory record; the app reads it back at start-up.

const MAGIC = Buffer.from('APK Sig Block 42');
const STAMP_ID = 0x4f524254; // 'ORBT'

function findEocd(buf) {
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 22 - 0xffff); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50 && i + 22 + buf.readUInt16LE(i + 20) === buf.length) return i;
  }
  throw new Error('EOCD not found');
}

function stampApk(apk, value) {
  const eocd = findEocd(apk);
  const cdOffset = apk.readUInt32LE(eocd + 16);
  if (!apk.subarray(cdOffset - 16, cdOffset).equals(MAGIC)) throw new Error('APK is not v2-signed');
  const blockSize = Number(apk.readBigUInt64LE(cdOffset - 24));
  const blockStart = cdOffset - blockSize - 8;
  if (Number(apk.readBigUInt64LE(blockStart)) !== blockSize) throw new Error('Corrupt signing block');

  // Collect existing pairs, dropping a previous stamp.
  const pairs = [];
  for (let p = blockStart + 8; p < cdOffset - 24;) {
    const len = Number(apk.readBigUInt64LE(p));
    const id = apk.readUInt32LE(p + 8);
    if (id !== STAMP_ID) pairs.push(apk.subarray(p, p + 8 + len));
    p += 8 + len;
  }
  const data = Buffer.from(value, 'utf8');
  const stamp = Buffer.alloc(12 + data.length);
  stamp.writeBigUInt64LE(BigInt(4 + data.length), 0);
  stamp.writeUInt32LE(STAMP_ID, 8);
  data.copy(stamp, 12);
  pairs.push(stamp);

  const body = Buffer.concat(pairs);
  const size = body.length + 8 + 16;
  const head = Buffer.alloc(8); head.writeBigUInt64LE(BigInt(size));
  const tail = Buffer.alloc(8); tail.writeBigUInt64LE(BigInt(size));
  const block = Buffer.concat([head, body, tail, MAGIC]);

  const newCd = blockStart + block.length;
  const rest = Buffer.from(apk.subarray(cdOffset));
  rest.writeUInt32LE(newCd, eocd - cdOffset + 16);
  return Buffer.concat([apk.subarray(0, blockStart), block, rest]);
}

module.exports = { stampApk, STAMP_ID };
