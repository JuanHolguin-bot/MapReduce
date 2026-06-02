from dataclasses import dataclass


@dataclass
class ShotMetrics:
    shots: int = 0
    goals: int = 0
    xg_sum: float = 0.0
    misses: int = 0

    def update(self, result: int, xg: float) -> None:
        self.shots += 1
        self.xg_sum += xg
        if result == 1:
            self.goals += 1
        else:
            self.misses += 1

    def merge(self, other: "ShotMetrics") -> None:
        self.shots += other.shots
        self.goals += other.goals
        self.misses += other.misses
        self.xg_sum += other.xg_sum
