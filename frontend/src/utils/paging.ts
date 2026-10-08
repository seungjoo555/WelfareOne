// 후보 목록을 3개씩 쪽으로 나누는 순수 함수. 서버가 준 우선순위 순서를 그대로 유지한다.
export const PAGE_SIZE = 3;

export const pageCount = (total: number, size: number = PAGE_SIZE): number =>
  total <= 0 ? 0 : Math.ceil(total / size);

// 후보 수가 바뀌어도(다른 상담으로 전환 등) 범위를 벗어나지 않도록 쪽 번호(0부터)를 보정한다.
export const clampPage = (page: number, total: number, size: number = PAGE_SIZE): number => {
  const last = Math.max(pageCount(total, size) - 1, 0);
  if (!Number.isFinite(page)) return 0;
  return Math.min(Math.max(Math.trunc(page), 0), last);
};

export const pageSlice = <T>(items: readonly T[], page: number, size: number = PAGE_SIZE): T[] => {
  const current = clampPage(page, items.length, size);
  return items.slice(current * size, current * size + size);
};

// 한 쪽에 다 들어가면 쪽 이동 버튼을 그리지 않는다.
export const needsPager = (total: number, size: number = PAGE_SIZE): boolean => total > size;
