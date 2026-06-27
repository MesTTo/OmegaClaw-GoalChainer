import {useEffect, useState} from 'react';
import {staticFile, delayRender, continueRender} from 'remotion';

const faces = `
@font-face { font-family: 'IBMPlexMono'; font-weight: 400; font-display: block;
  src: url(${staticFile('fonts/plexmono-400.woff2')}) format('woff2'); }
@font-face { font-family: 'IBMPlexMono'; font-weight: 600; font-display: block;
  src: url(${staticFile('fonts/plexmono-600.woff2')}) format('woff2'); }
@font-face { font-family: 'Fraunces'; font-weight: 400; font-display: block;
  src: url(${staticFile('fonts/fraunces-400.woff2')}) format('woff2'); }
@font-face { font-family: 'Fraunces'; font-weight: 600; font-display: block;
  src: url(${staticFile('fonts/fraunces-600.woff2')}) format('woff2'); }
@font-face { font-family: 'IBMPlexSans'; font-weight: 500; font-display: block;
  src: url(${staticFile('fonts/plexsans-500.woff2')}) format('woff2'); }
`;

export const Fonts: React.FC = () => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = faces;
    document.head.appendChild(style);
    Promise.all([
      document.fonts.load("600 22px 'IBMPlexMono'"),
      document.fonts.load("400 22px 'IBMPlexMono'"),
      document.fonts.load("600 40px 'Fraunces'"),
      document.fonts.load("500 20px 'IBMPlexSans'"),
    ])
      .then(() => document.fonts.ready)
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle]);
  return null;
};
