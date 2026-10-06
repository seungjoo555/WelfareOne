import type { Regions } from "../../types/contract";

interface Props {
  regions: Regions;
  level1: string;
  level2: string;
  onChange: (level1: string, level2: string) => void;
}

// 시·도 → 시·군·구 연동 드롭다운. 시·군·구가 없는 지역은 하위 선택을 비활성화한다.
export function RegionSelect({ regions, level1, level2, onChange }: Props) {
  const districts = level1 ? (regions[level1] ?? []) : [];
  return (
    <>
      <label className="field">
        <span>시·도</span>
        <select value={level1} onChange={(e) => onChange(e.target.value, "")}>
          <option value="">선택하세요</option>
          {Object.keys(regions).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>시·군·구</span>
        <select
          value={level2}
          disabled={!level1 || districts.length === 0}
          onChange={(e) => onChange(level1, e.target.value)}
        >
          <option value="">
            {level1 && districts.length === 0 ? "하위 지역 없음" : "선택 안 함"}
          </option>
          {districts.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
