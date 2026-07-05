import bcryptjs from 'bcryptjs';
import jwt from 'jsonwebtoken';

const SECRET_KEY = process.env.SECRET_KEY || 'media-server-secret-key-1234567890';

export function hashPassword(password: string): string {
  const salt = bcryptjs.genSaltSync(10);
  return bcryptjs.hashSync(password, salt);
}

export function comparePassword(password: string, hash: string): boolean {
  try {
    return bcryptjs.compareSync(password, hash);
  } catch (e) {
    return false;
  }
}

export function generateToken(userId: string): string {
  return jwt.sign({ sub: userId }, SECRET_KEY, { expiresIn: '7d' });
}

export interface JwtPayload {
  sub: string;
}

export function verifyToken(token: string): string | null {
  try {
    const payload = jwt.verify(token, SECRET_KEY) as JwtPayload;
    return payload.sub || null;
  } catch (e) {
    return null;
  }
}
