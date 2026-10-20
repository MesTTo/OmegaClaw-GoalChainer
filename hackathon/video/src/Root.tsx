// Purpose: register the video package's three compositions, each a historical film of GoalChainer
// before its domain-request migration, shown with the historical label over every frame.
import {Composition} from 'remotion';
import {OmegaClawHackathonVideo} from './video/OmegaClawHackathonVideo';
import {GoalChainerFilm, timeline} from './film/GoalChainerFilm';
import {ExplainerFilm, explainerTimeline} from './film/ExplainerFilm';
import {historical} from './HistoricalLabel';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const DURATION_IN_FRAMES = FPS * 120 - 2;

// Every registered composition records the June 2026 GoalChainer, so each carries the label; one
// registered without it would read as current behaviour.
// am[implements a-fh-label-1018@2f54e2]
const HistoricalExplainerFilm = historical(ExplainerFilm);
const HistoricalGoalChainerFilm = historical(GoalChainerFilm);
const HistoricalOmegaClawHackathonVideo = historical(OmegaClawHackathonVideo);

// am[implements a-fh-label-1018@2f54e2]
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        component={HistoricalExplainerFilm}
        durationInFrames={explainerTimeline().total}
        fps={FPS}
        height={HEIGHT}
        id="GoalChainerExplainer"
        width={WIDTH}
      />
      <Composition
        component={HistoricalGoalChainerFilm}
        durationInFrames={timeline().total}
        fps={FPS}
        height={HEIGHT}
        id="GoalChainer"
        width={WIDTH}
      />
      <Composition
        component={HistoricalOmegaClawHackathonVideo}
        durationInFrames={DURATION_IN_FRAMES}
        fps={FPS}
        height={HEIGHT}
        id="OmegaClawHackathon"
        width={WIDTH}
      />
    </>
  );
};
