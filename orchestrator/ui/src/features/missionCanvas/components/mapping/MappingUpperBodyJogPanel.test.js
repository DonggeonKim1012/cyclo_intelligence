import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useNavigationRosTopic } from "../../../../hooks/useNavigationRosTopic";
import MappingUpperBodyJogPanel, { headPitchJogTarget, jogWithinLimits } from "./MappingUpperBodyJogPanel";

jest.mock("../../../../hooks/useNavigationRosTopic", () => ({
  useNavigationRosTopic: jest.fn(),
}));

const stoppedOdom = () => ({
  data: { twist: { twist: { linear: { x: 0, y: 0 }, angular: { z: 0 } } } },
});

test("head outside the motor range recovers inside its raw limit and holds the other joint", async () => {
  let odom = stoppedOdom();
  useNavigationRosTopic.mockImplementation((topic) => ({
    topicData: topic === "/joint_states"
      ? { data: { name: ["head_joint1", "head_joint2"], position: [0.84, 0] } }
      : topic === "/odom" ? odom : null,
  }));
  const publish = jest.fn().mockResolvedValue(undefined);
  const props = { disabled: false, onPublishRosTopic: publish, onMessage: jest.fn() };
  const view = render(<MappingUpperBodyJogPanel {...props} />);

  fireEvent.click(screen.getByRole("button", { name: "Activate" }));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Look Up" })));
  await waitFor(() => expect(publish).toHaveBeenCalledTimes(1));
  odom = stoppedOdom();
  view.rerender(<MappingUpperBodyJogPanel {...props} />);
  odom = stoppedOdom();
  view.rerender(<MappingUpperBodyJogPanel {...props} />);
  await waitFor(() => expect(publish).toHaveBeenCalledTimes(2));
  const positions = publish.mock.calls[1][2].points[0].positions;
  expect(positions[0]).toBeCloseTo(Math.PI / 4 - 0.01);
  expect((positions[0] + Math.PI) / (2 * Math.PI / 4096)).toBeLessThan(2560);
  expect(positions[1]).toBe(0);
});

test("out of range head cannot jog farther outward", () => {
  expect(jogWithinLimits(0.84, 0.05, { lower: -0.2267, upper: 0.6901 })).toBe(0.84);
  expect(jogWithinLimits(0.84, 0, { lower: -0.2267, upper: 0.6901 })).toBe(0.84);
  expect(Number.isNaN(headPitchJogTarget(0.95, -0.02, { lower: -0.2267, upper: 0.6901 }))).toBe(true);
});
