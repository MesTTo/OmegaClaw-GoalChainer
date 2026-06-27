import {Composition} from 'remotion';
import {OmegaClawHackathonVideo} from './video/OmegaClawHackathonVideo';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const DURATION_IN_FRAMES = FPS * 180;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      component={OmegaClawHackathonVideo}
      durationInFrames={DURATION_IN_FRAMES}
      fps={FPS}
      height={HEIGHT}
      id="OmegaClawHackathon"
      width={WIDTH}
    />
  );
};
