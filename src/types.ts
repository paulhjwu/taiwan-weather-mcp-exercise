export interface Env {
  CWA_API_KEY: string;
  SERVER_NAME: string;
  SERVER_VERSION: string;
}

export interface CwaApiResponse<T = unknown> {
  success: string;
  result: {
    resource_id: string;
    fields: unknown[];
  };
  records: T;
}

export interface ForecastLocation {
  locationName: string;
  weatherElement: WeatherElement[];
}

export interface WeatherElement {
  elementName: string;
  description: string;
  time: TimeEntry[];
}

export interface TimeEntry {
  startTime: string;
  endTime: string;
  elementValue: { value: string; measures: string }[];
}

// F-C0032-001 (36hr forecast) actual response shape — distinct from the
// generic TimeEntry above, which does not match what CWA returns for this
// dataset.
export interface Forecast36hrLocation {
  locationName: string;
  weatherElement: Forecast36hrWeatherElement[];
}

export interface Forecast36hrWeatherElement {
  elementName: string;
  description?: string;
  time: Forecast36hrTimeEntry[];
}

export interface Forecast36hrTimeEntry {
  startTime: string;
  endTime: string;
  // parameterName holds the actual value (e.g. "30", "舒適至悶熱") for every
  // element except Wx, where it's the description and parameterValue is the
  // numeric weather code instead.
  parameter: { parameterName: string; parameterUnit?: string; parameterValue?: string };
}

export interface EarthquakeRecord {
  EarthquakeNo: number;
  ReportContent: string;
  ReportColor: string;
  EarthquakeInfo: {
    OriginTime: string;
    Source: string;
    FocalDepth: number;
    EpiCenter: { Location: string; EpiCenterLat: number; EpiCenterLon: number };
    EarthquakeMagnitude: { MagnitudeType: string; MagnitudeValue: number };
  };
}

export interface ToolResult {
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}
