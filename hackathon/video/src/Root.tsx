import {Composition} from 'remotion';
import {OmegaClawHackathonVideo} from './video/OmegaClawHackathonVideo';
import {GoalChainerFilm, timeline} from './film/GoalChainerFilm';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const DURATION_IN_FRAMES = FPS * 120 - 2;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        component={GoalChainerFilm}
        durationInFrames={timeline().total}
        fps={FPS}
        height={HEIGHT}
        id="GoalChainer"
        width={WIDTH}
      />
      <Composition
        component={OmegaClawHackathonVideo}
        durationInFrames={DURATION_IN_FRAMES}
        fps={FPS}
        height={HEIGHT}
        id="OmegaClawHackathon"
        width={WIDTH}
      />
    </>
  );
};
