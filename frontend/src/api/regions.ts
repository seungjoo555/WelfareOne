import type { Regions } from "../types/contract";
import { request } from "./client";

export const getRegions = () => request<Regions>("/regions");
