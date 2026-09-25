export const BINARY_AUDIO_EXTENSIONS = Object.freeze([
  'mp3', 'wav', 'wave', 'ogg', 'oga', 'opus', 'm4a', 'aac', 'flac',
  'weba', 'webm', 'aif', 'aiff', 'caf', 'mid', 'midi',
]);

const extensionPattern = BINARY_AUDIO_EXTENSIONS.join('|');
const referencePattern = new RegExp(
  String.raw`\.(?:${extensionPattern})(?:[?#'"\x60)\s]|$)`,
  'i',
);

export const hasBinaryAudioExtension = (value) => {
  const clean = String(value || '').split(/[?#]/, 1)[0].toLowerCase();
  return BINARY_AUDIO_EXTENSIONS.some((extension) => clean.endsWith(`.${extension}`));
};

export const containsBinaryAudioReference = (value) => referencePattern.test(String(value || ''));
