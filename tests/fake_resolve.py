"""Resolve simulado con el subconjunto de la API que usa kresolve.

Permite probar TitleBuilder sin Resolve. ``record_mode`` y ``end_inclusive``
simulan las dos ambigüedades de AppendToTimeline que la calibración resuelve.
"""

from __future__ import annotations


class FakeTool:
    def __init__(self, name="Template"):
        self.name = name
        self.inputs = {"StyledText": "", "Start": 0.0, "End": 1.0}

    def SetInput(self, name, value):
        self.inputs[name] = value
        return True

    def GetInput(self, name):
        return self.inputs.get(name)

    def GetInputList(self):
        return {}


class FakeComp:
    def __init__(self, tool_name="Template"):
        self.tool = FakeTool(tool_name)
        self.locked = 0

    def FindTool(self, name):
        return self.tool if name == self.tool.name else None

    def GetToolList(self, selected=False, tool_id=None):
        return {1: self.tool}

    def Lock(self):
        self.locked += 1

    def Unlock(self):
        self.locked -= 1


class FakeMediaPoolItem:
    def __init__(self, name, type_="Fusion Title", tool_name="Template"):
        self.name = name
        self.type = type_
        self.tool_name = tool_name

    def GetName(self):
        return self.name

    def GetClipProperty(self, key=None):
        props = {"Type": self.type}
        return props if key is None else props.get(key)


class FakeFolder:
    def __init__(self, clips=(), subs=()):
        self.clips = list(clips)
        self.subs = list(subs)

    def GetClipList(self):
        return self.clips

    def GetSubFolderList(self):
        return self.subs


class FakeTimelineItem:
    def __init__(self, timeline, track, start, duration, mp_item):
        self.timeline = timeline
        self.track = track
        self.start = start
        self.duration = duration
        self.mp_item = mp_item
        self.comp = FakeComp(mp_item.tool_name) if mp_item else None
        self.name = mp_item.name if mp_item else "clip"
        self.color = None

    def GetStart(self, subframe=False):
        return float(self.start)

    def GetDuration(self, subframe=False):
        return float(self.duration)

    def GetEnd(self, subframe=False):
        return float(self.start + self.duration)

    def GetTrackTypeAndIndex(self):
        return ["video", self.track]

    def GetFusionCompByIndex(self, i):
        return self.comp

    def SetName(self, name):
        self.name = name
        return True

    def GetName(self):
        return self.name

    def SetClipColor(self, c):
        self.color = c
        return True

    def SetPosition(self, pos, *a):
        self.start = int(pos.get("startFrame", self.start))
        self.track = int(pos.get("trackIndex", self.track))
        return True


class FakeTimeline:
    def __init__(self, start_frame=86400, fps="24", name="Timeline 1"):
        self.start_frame = start_frame
        self.fps = fps
        self.name = name
        self.tracks = [{"name": "Video 1", "items": [], "locked": False}]
        self.tracks[0]["items"].append(FakeTimelineItem(self, 1, start_frame, 2000, None))  # clip del usuario

    def GetName(self):
        return self.name

    def GetStartFrame(self):
        return self.start_frame

    def GetSettings(self):
        return {"timelineFrameRate": self.fps}

    def GetTrackCount(self, kind):
        return len(self.tracks)

    def AddTrack(self, kind, sub=None):
        self.tracks.append({"name": f"Video {len(self.tracks) + 1}", "items": [], "locked": False})
        return True

    def DeleteTrack(self, kind, idx):
        del self.tracks[idx - 1]
        return True

    def GetTrackName(self, kind, idx):
        return self.tracks[idx - 1]["name"]

    def SetTrackName(self, kind, idx, name):
        self.tracks[idx - 1]["name"] = name
        return True

    def GetIsTrackLocked(self, kind, idx):
        return self.tracks[idx - 1]["locked"]

    def SetTrackLock(self, kind, idx, locked):
        self.tracks[idx - 1]["locked"] = locked
        return True

    def GetItemListInTrack(self, kind, idx):
        return list(self.tracks[idx - 1]["items"])

    def DeleteClips(self, items, ripple=False):
        for t in self.tracks:
            t["items"] = [i for i in t["items"] if i not in items]
        return True


class FakeMediaPool:
    def __init__(self, timeline, items, record_mode="absolute", end_inclusive=True):
        self.timeline = timeline
        self.root = FakeFolder(clips=[FakeMediaPoolItem("Video.mp4", "Video + Audio")],
                               subs=[FakeFolder(clips=items)])
        self.record_mode = record_mode
        self.end_inclusive = end_inclusive
        self.append_calls = 0

    def GetRootFolder(self):
        return self.root

    def AppendToTimeline(self, infos):
        self.append_calls += 1
        out = []
        for info in infos:
            track = info["trackIndex"]
            if self.timeline.tracks[track - 1]["locked"]:
                out.append(None)
                continue
            rec = int(info["recordFrame"])
            start = rec if self.record_mode == "absolute" else self.timeline.start_frame + rec
            dur = int(info["endFrame"]) - int(info["startFrame"]) + (1 if self.end_inclusive else 0)
            item = FakeTimelineItem(self.timeline, track, start, dur, info["mediaPoolItem"])
            self.timeline.tracks[track - 1]["items"].append(item)
            out.append(item)
        return out

    def CreateEmptyTimeline(self, name):
        return FakeTimeline(self.timeline.start_frame, self.timeline.fps, name)


class FakeProject:
    def __init__(self, client):
        self.client = client

    def GetName(self):
        return "Proyecto de prueba"

    def SetCurrentTimeline(self, tl):
        self.client.timeline = tl
        self.client.media_pool.timeline = tl
        return True


class FakeClient:
    """Sustituye a ResolveClient (misma interfaz pública que usa TitleBuilder)."""

    product = "DaVinci Resolve (simulado)"
    version = "21.2"

    def __init__(self, template_name="kresolve_template", **mp_kwargs):
        self.timeline = FakeTimeline()
        self.template = FakeMediaPoolItem(template_name)
        self.media_pool = FakeMediaPool(self.timeline, [self.template], **mp_kwargs)
        self.project = FakeProject(self)

    def refresh(self):
        pass

    @property
    def fps(self):
        return 24.0

    @property
    def fps_raw(self):
        return "24"

    @property
    def start_frame(self):
        return self.timeline.start_frame

    @property
    def timeline_name(self):
        return self.timeline.name
