import React, { useState, useEffect, useCallback } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Modal,
  ActivityIndicator,
} from "react-native";
import { theme } from "../styles/theme";
import { gatewayClient } from "../services/gateway";
import { offlineStore } from "../services/offline-store";
import { workstationStore } from "../services/workstation-store";
import { ApiTask, CalendarEvent } from "../types/vesper";

type AgendaSubTab = "overview" | "tasks" | "calendar" | "urgent" | "completed";

export const AgendaView: React.FC = () => {
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [activeTab, setActiveTab] = useState<AgendaSubTab>("overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isOffline, setIsOffline] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  // Directives Capsule Bar Input
  const [directiveInput, setDirectiveInput] = useState("");

  // New Deliverable Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newPriority, setNewPriority] = useState<"normal" | "high" | "urgent">("normal");
  const [newDeadline, setNewDeadline] = useState("");

  const loadData = useCallback(async () => {
    setIsRefreshing(true);

    // 1. Immediately hydrate from offline cache
    const [cTasks, cEvents, pCount] = await Promise.all([
      offlineStore.getCachedTasks(),
      offlineStore.getCachedCalendarEvents(),
      offlineStore.getPendingCount(),
    ]);

    if (cTasks && cTasks.length > 0) setTasks(cTasks);
    if (cEvents && cEvents.length > 0) setCalendarEvents(cEvents);
    setPendingCount(pCount);

    // 2. Fetch live data if reachable
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/tasks`);
      if (res.ok) {
        const data = await res.json();
        if (data.tasks) {
          setTasks(data.tasks);
          offlineStore.saveCachedTasks(data.tasks);
        }
        if (data.calendar_events) {
          setCalendarEvents(data.calendar_events);
          offlineStore.saveCachedCalendarEvents(data.calendar_events);
        }
        setIsOffline(false);
      } else {
        setIsOffline(true);
      }
    } catch (e) {
      console.warn("[AgendaView] Network fetch error, using cached state:", e);
      setIsOffline(true);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();

    const unsub = offlineStore.subscribeSync((_syncing, count) => {
      setPendingCount(count);
    });

    return () => unsub();
  }, [loadData]);

  const handleToggleTask = async (task: ApiTask) => {
    const updatedTasks = tasks.map((t) =>
      t.id === task.id ? { ...t, done: !t.done } : t
    );
    setTasks(updatedTasks);
    await offlineStore.saveCachedTasks(updatedTasks);

    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/tasks/${task.id}/toggle`, { method: "PATCH" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch {
      await offlineStore.enqueueOfflineTask("TOGGLE", { id: task.id });
      setIsOffline(true);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    const updatedTasks = tasks.filter((t) => t.id !== taskId);
    setTasks(updatedTasks);
    await offlineStore.saveCachedTasks(updatedTasks);

    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/tasks/${taskId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch {
      await offlineStore.enqueueOfflineTask("DELETE", { id: taskId });
      setIsOffline(true);
    }
  };

  const handleCreateTask = async () => {
    if (!newTitle.trim()) return;

    const payload = {
      title: newTitle.trim(),
      priority: newPriority,
      deadline: newDeadline.trim() || null,
      metadata: { source: "mobile_agenda" },
    };

    const optimisticTask: ApiTask = {
      id: `local_task_${Date.now()}`,
      title: newTitle.trim(),
      priority: newPriority,
      deadline: newDeadline.trim() || undefined,
      done: false,
      category: "today",
    };

    const updatedTasks = [optimisticTask, ...tasks];
    setTasks(updatedTasks);
    await offlineStore.saveCachedTasks(updatedTasks);

    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const created = await res.json();
        optimisticTask.id = created.id || optimisticTask.id;
        await offlineStore.saveCachedTasks(updatedTasks);
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch {
      await offlineStore.enqueueOfflineTask("CREATE", payload);
      setIsOffline(true);
    } finally {
      setNewTitle("");
      setNewDeadline("");
      setNewPriority("normal");
      setIsModalOpen(false);
    }
  };

  const handleDirectiveSubmit = () => {
    if (!directiveInput.trim()) return;
    const input = directiveInput.trim();
    setDirectiveInput("");

    // If starts with "+" or "task" or "todo", create task immediately
    const clean = input.replace(/^(\+|task\s+|todo\s+)/i, "").trim();
    if (clean) {
      setNewTitle(clean);
      setNewPriority("normal");
      setIsModalOpen(true);
    } else {
      // Natural language directive to Alfred
      workstationStore.sendUserMessage(input);
    }
  };

  // Metrics computation
  const pendingTasks = tasks.filter((t) => !t.done);
  const completedTasks = tasks.filter((t) => t.done);
  const urgentTasks = tasks.filter((t) => !t.done && (t.priority === "urgent" || t.priority === "high"));
  const completionRate = tasks.length > 0 ? Math.round((completedTasks.length / tasks.length) * 100) : 100;
  const topTask = urgentTasks[0] || pendingTasks[0] || null;

  // Filtered tasks based on activeTab and searchQuery
  const filteredTasks = tasks.filter((t) => {
    if (activeTab === "urgent" && t.priority !== "urgent" && t.priority !== "high") return false;
    if (activeTab === "completed" && !t.done) return false;
    if (activeTab !== "completed" && t.done && activeTab !== "overview") return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        t.title.toLowerCase().includes(q) ||
        (t.tag && t.tag.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* ── Section 1: Aerospace Header & Tactical Telemetry Deck ── */}
      <View style={styles.headerOuterBezel}>
        <View style={styles.headerInnerCore}>
          <View style={styles.greetingBlock}>
            <View style={styles.systemTagRow}>
              <View style={[styles.pulseDot, isOffline && styles.pulseDotOffline]} />
              <Text style={styles.systemTagText}>
                {isOffline ? "OFFLINE CACHE" : "AGENDA NOMINAL"}
              </Text>
              <Text style={styles.systemSeparator}>•</Text>
              <Text style={styles.systemNodeText}>
                {pendingCount > 0 ? `SYNC (${pendingCount})` : "TASK-01"}
              </Text>
            </View>
            <Text style={styles.greetingTitle}>Tactical Flight Deck</Text>
            <Text style={styles.greetingSub} numberOfLines={2}>
              Autonomous task queue &amp; Google Calendar sync.
            </Text>
          </View>

          {/* Precision Aerospace Metric Capsule */}
          <View style={styles.chronoCapsule}>
            <View style={styles.chronoTopRow}>
              <Text style={styles.chronoDigits} numberOfLines={1}>
                {pendingTasks.length} PENDING
              </Text>
            </View>
            <Text style={styles.chronoDate} numberOfLines={1}>
              {completionRate}% DONE • {isOffline ? "CACHED" : "LIVE"}
            </Text>
          </View>
        </View>
      </View>

      {/* ── Section 2: Directives Capsule Bar ── */}
      <View style={styles.directiveOuterBezel}>
        <View style={styles.directiveInnerCore}>
          <View style={styles.directiveInputRow}>
            <Text style={styles.directivePrefix}>agenda &gt;</Text>
            <TextInput
              style={styles.directiveInput}
              value={directiveInput}
              onChangeText={setDirectiveInput}
              placeholder="Add task or prompt Alfred..."
              placeholderTextColor="#8E887E"
              onSubmitEditing={handleDirectiveSubmit}
              returnKeyType="send"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TouchableOpacity
              style={[
                styles.directiveRunBtn,
                !directiveInput.trim() && styles.directiveRunBtnDisabled,
              ]}
              onPress={handleDirectiveSubmit}
              disabled={!directiveInput.trim()}
              activeOpacity={0.8}
            >
              <Text
                style={[
                  styles.directiveRunText,
                  !directiveInput.trim() && styles.directiveRunTextDisabled,
                ]}
              >
                POST
              </Text>
            </TouchableOpacity>
          </View>

          {/* Action Chips */}
          <View style={styles.chipsRow}>
            <TouchableOpacity
              style={styles.chipPill}
              onPress={() => setIsModalOpen(true)}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>+ DELIVERABLE</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.chipPill}
              onPress={() => setActiveTab("urgent")}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>URGENT ({urgentTasks.length})</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.chipPill}
              onPress={() => setActiveTab("calendar")}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>CALENDAR ({calendarEvents.length})</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.chipPill}
              onPress={loadData}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>REFRESH</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* ── Section 3: Segmented Aerospace Subtabs Switcher ── */}
      <View style={styles.subTabsOuter}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.subTabsScrollContent}
        >
          {(
            [
              { id: "overview", label: "OVERVIEW" },
              { id: "tasks", label: `TASKS (${pendingTasks.length})` },
              { id: "calendar", label: `SCHEDULE (${calendarEvents.length})` },
              { id: "urgent", label: `URGENT (${urgentTasks.length})` },
              { id: "completed", label: `ARCHIVE (${completedTasks.length})` },
            ] as const
          ).map((tab) => {
            const active = activeTab === tab.id;
            return (
              <TouchableOpacity
                key={tab.id}
                style={[styles.subTabPill, active && styles.subTabPillActive]}
                onPress={() => setActiveTab(tab.id as AgendaSubTab)}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    styles.subTabPillText,
                    active && styles.subTabPillTextActive,
                  ]}
                  numberOfLines={1}
                >
                  {tab.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* ── Search Filter Strip (if in tasks or completed tabs) ── */}
      {(activeTab === "tasks" || activeTab === "completed" || activeTab === "urgent") && (
        <View style={styles.searchBarWrap}>
          <TextInput
            style={styles.aerospaceSearchInput}
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Filter deliverables by keyword or tag..."
            placeholderTextColor="#8E887E"
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      )}

      {/* ── Section 4: Subtab Content Decks ── */}

      {/* 4A: OVERVIEW TAB (MAIN FLIGHT DECK) */}
      {activeTab === "overview" && (
        <View style={styles.tabContentCol}>
          {/* Hero Bento Card: Tactical Horizon Focus */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.bentoEyebrow}>TACTICAL HORIZON FOCUS</Text>
                </View>
                <View style={styles.bentoLinkCapsule}>
                  <Text style={styles.bentoLinkText}>
                    {topTask ? (topTask.priority === "urgent" ? "CRITICAL" : "IMMINENT") : "BALANCED"}
                  </Text>
                </View>
              </View>

              {topTask ? (
                <View style={styles.topTaskCard}>
                  <View style={styles.topTaskHeaderRow}>
                    <View style={styles.topTaskBadgeWrap}>
                      <View
                        style={[
                          styles.priorityDot,
                          topTask.priority === "urgent"
                            ? { backgroundColor: theme.colors.crimson }
                            : { backgroundColor: theme.colors.amber },
                        ]}
                      />
                      <Text style={styles.topTaskPriorityText} numberOfLines={1}>
                        {(topTask.priority || "NORMAL").toUpperCase()} PRIORITY
                      </Text>
                    </View>
                    {topTask.deadline && (
                      <View style={styles.topTaskDeadlineBadge}>
                        <Text style={styles.topTaskDeadlineText} numberOfLines={1}>
                          DUE: {topTask.deadline}
                        </Text>
                      </View>
                    )}
                  </View>

                  <Text style={styles.topTaskTitleText} numberOfLines={3}>
                    {topTask.title}
                  </Text>

                  <View style={styles.topTaskActionRow}>
                    <TouchableOpacity
                      style={styles.topTaskCompleteBtn}
                      onPress={() => handleToggleTask(topTask)}
                      activeOpacity={0.8}
                    >
                      <Text style={styles.topTaskCompleteText}>MARK COMPLETE</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.topTaskDetailsBtn}
                      onPress={() => setActiveTab("tasks")}
                      activeOpacity={0.8}
                    >
                      <Text style={styles.topTaskDetailsText}>ALL TASKS &gt;</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <View style={styles.emptyTopTaskBox}>
                  <Text style={styles.emptyTopTaskTitle}>Zero Outstanding Deliverables</Text>
                  <Text style={styles.emptyTopTaskSub}>
                    All prioritized work completed. Tap + DELIVERABLE to queue next goal.
                  </Text>
                </View>
              )}

              {/* Telemetry Completion & Load Gauges without any text clipping */}
              <View style={styles.gaugesContainerRow}>
                {/* Completion Ratio Gauge */}
                <View style={styles.gaugeBox}>
                  <View style={styles.gaugeHeader}>
                    <Text style={styles.gaugeLabel} numberOfLines={1}>
                      COMPLETION
                    </Text>
                    <Text
                      style={[styles.gaugeAmount, { color: theme.colors.emerald }]}
                      numberOfLines={1}
                    >
                      {completionRate}%
                    </Text>
                  </View>
                  <View style={styles.gaugeTrack}>
                    <View
                      style={[
                        styles.gaugeFill,
                        styles.gaugeFillEmerald,
                        { width: `${Math.max(5, completionRate)}%` },
                      ]}
                    />
                  </View>
                  <Text style={styles.gaugeSubText} numberOfLines={1}>
                    {completedTasks.length} of {tasks.length} delivered
                  </Text>
                </View>

                {/* Calendar Schedule Load Gauge */}
                <View style={styles.gaugeBox}>
                  <View style={styles.gaugeHeader}>
                    <Text style={styles.gaugeLabel} numberOfLines={1}>
                      SCHEDULE
                    </Text>
                    <Text
                      style={[styles.gaugeAmount, { color: theme.colors.amber }]}
                      numberOfLines={1}
                    >
                      {calendarEvents.length} EVENTS
                    </Text>
                  </View>
                  <View style={styles.gaugeTrack}>
                    <View
                      style={[
                        styles.gaugeFill,
                        styles.gaugeFillAmber,
                        {
                          width: `${Math.min(
                            100,
                            Math.max(10, calendarEvents.length * 25)
                          )}%`,
                        },
                      ]}
                    />
                  </View>
                  <Text style={styles.gaugeSubText} numberOfLines={1}>
                    {calendarEvents.length > 0
                      ? "Google Calendar live"
                      : "No meetings today"}
                  </Text>
                </View>
              </View>
            </View>
          </View>

          {/* ── IMMINENT APPOINTMENTS: Google Calendar Pods ── */}
          {calendarEvents.length > 0 && (
            <View style={styles.heroOuterBezel}>
              <View style={styles.heroInnerCore}>
                <View style={styles.bentoHeaderRow}>
                  <View style={styles.bentoTagWrap}>
                    <View style={styles.bentoEmeraldDot} />
                    <Text style={styles.bentoEyebrow}>GOOGLE CALENDAR</Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => setActiveTab("calendar")}
                    activeOpacity={0.7}
                    style={styles.bentoLinkCapsule}
                  >
                    <Text style={styles.bentoLinkText}>
                      ALL ({calendarEvents.length}) &gt;
                    </Text>
                  </TouchableOpacity>
                </View>

                <View style={styles.scheduleGrid}>
                  {calendarEvents.slice(0, 3).map((evt, idx) => (
                    <View key={idx} style={styles.appointmentPodOuter}>
                      <View style={styles.appointmentPodInner}>
                        <View style={styles.appointmentTimeCol}>
                          <Text style={styles.appointmentTimeText}>
                            {evt.time || evt.start || "Today"}
                          </Text>
                          <View style={styles.appointmentVerifiedDot} />
                        </View>
                        <View style={styles.appointmentBodyCol}>
                          <Text style={styles.appointmentTitleText} numberOfLines={1}>
                            {evt.summary || evt.title}
                          </Text>
                          {evt.location && (
                            <Text style={styles.appointmentLocationText} numberOfLines={1}>
                              {evt.location}
                            </Text>
                          )}
                        </View>
                      </View>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          )}

          {/* ── RECENT ACTIVE DELIVERABLES: Top 5 Tasks ── */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.bentoEyebrow}>TACTICAL QUEUE</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setActiveTab("tasks")}
                  activeOpacity={0.7}
                  style={styles.bentoLinkCapsule}
                >
                  <Text style={styles.bentoLinkText}>
                    ALL ({pendingTasks.length}) &gt;
                  </Text>
                </TouchableOpacity>
              </View>

              {pendingTasks.length === 0 ? (
                <View style={styles.emptyTasksPod}>
                  <Text style={styles.emptyTasksTitle}>All Deliverables Completed</Text>
                  <Text style={styles.emptyTasksSub}>
                    Zero outstanding tasks queued on host cluster.
                  </Text>
                </View>
              ) : (
                pendingTasks.slice(0, 5).map((task) => (
                  <View key={task.id} style={styles.taskPodOuter}>
                    <View style={styles.taskPodInner}>
                      <TouchableOpacity
                        style={[styles.taskCheckbox, task.done && styles.taskCheckboxDone]}
                        onPress={() => handleToggleTask(task)}
                        activeOpacity={0.7}
                      >
                        {task.done && <Text style={styles.taskCheckGlyph}>✓</Text>}
                      </TouchableOpacity>

                      <View style={styles.taskBodyCol}>
                        <Text style={styles.taskTitleText} numberOfLines={2}>
                          {task.title}
                        </Text>
                        <View style={styles.taskMetaRow}>
                          {task.priority === "urgent" && (
                            <View style={styles.urgentBadge}>
                              <Text style={styles.urgentBadgeText}>URGENT</Text>
                            </View>
                          )}
                          {task.priority === "high" && (
                            <View style={styles.highBadge}>
                              <Text style={styles.highBadgeText}>HIGH</Text>
                            </View>
                          )}
                          {task.deadline && (
                            <Text style={styles.taskDeadlineText}>Due: {task.deadline}</Text>
                          )}
                          {task.age_label && (
                            <Text style={styles.taskAgeText}>{task.age_label}</Text>
                          )}
                        </View>
                      </View>

                      <TouchableOpacity
                        style={styles.taskDeleteBtn}
                        onPress={() => handleDeleteTask(task.id)}
                        activeOpacity={0.7}
                      >
                        <Text style={styles.taskDeleteGlyph}>✕</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ))
              )}
            </View>
          </View>
        </View>
      )}

      {/* 4B: DEDICATED TASKS SUBTAB */}
      {(activeTab === "tasks" || activeTab === "urgent" || activeTab === "completed") && (
        <View style={styles.tabContentCol}>
          <View style={styles.streamHeaderRow}>
            <Text style={styles.streamHeaderTitle}>
              {activeTab === "urgent"
                ? `CRITICAL & HIGH PRIORITY (${filteredTasks.length})`
                : activeTab === "completed"
                ? `DELIVERED ARCHIVES (${filteredTasks.length})`
                : `DELIVERABLES STREAM (${filteredTasks.length})`}
            </Text>
            {isRefreshing && <ActivityIndicator size="small" color={theme.colors.boneWhite} />}
          </View>

          {filteredTasks.length === 0 ? (
            <View style={styles.emptyOuterBezel}>
              <View style={styles.emptyInnerCore}>
                <Text style={styles.emptyTitle}>No Deliverables Recorded</Text>
                <Text style={styles.emptySubtitle}>
                  {activeTab === "completed"
                    ? "Completed tasks will be cataloged here."
                    : "No matching criteria found. Type in directive bar to commit a new task."}
                </Text>
              </View>
            </View>
          ) : (
            filteredTasks.map((task) => (
              <View key={task.id} style={styles.taskPodOuter}>
                <View style={styles.taskPodInner}>
                  <TouchableOpacity
                    style={[styles.taskCheckbox, task.done && styles.taskCheckboxDone]}
                    onPress={() => handleToggleTask(task)}
                    activeOpacity={0.7}
                  >
                    {task.done && <Text style={styles.taskCheckGlyph}>✓</Text>}
                  </TouchableOpacity>

                  <View style={styles.taskBodyCol}>
                    <Text
                      style={[styles.taskTitleText, task.done && styles.taskTitleTextDone]}
                      numberOfLines={3}
                    >
                      {task.title}
                    </Text>
                    <View style={styles.taskMetaRow}>
                      {task.priority === "urgent" && (
                        <View style={styles.urgentBadge}>
                          <Text style={styles.urgentBadgeText}>URGENT</Text>
                        </View>
                      )}
                      {task.priority === "high" && (
                        <View style={styles.highBadge}>
                          <Text style={styles.highBadgeText}>HIGH</Text>
                        </View>
                      )}
                      {task.deadline && (
                        <Text style={styles.taskDeadlineText}>Due: {task.deadline}</Text>
                      )}
                      {task.age_label && (
                        <Text style={styles.taskAgeText}>{task.age_label}</Text>
                      )}
                    </View>
                  </View>

                  <TouchableOpacity
                    style={styles.taskDeleteBtn}
                    onPress={() => handleDeleteTask(task.id)}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.taskDeleteGlyph}>✕</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      {/* 4C: DEDICATED CALENDAR SCHEDULE SUBTAB */}
      {activeTab === "calendar" && (
        <View style={styles.tabContentCol}>
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoEmeraldDot} />
                  <Text style={styles.bentoEyebrow}>GOOGLE CALENDAR ROSTER</Text>
                </View>
                <View style={styles.bentoLinkCapsule}>
                  <Text style={styles.bentoLinkText}>VERIFIED TIMELINE</Text>
                </View>
              </View>

              {calendarEvents.length === 0 ? (
                <View style={styles.emptyTasksPod}>
                  <Text style={styles.emptyTasksTitle}>No Calendar Appointments</Text>
                  <Text style={styles.emptyTasksSub}>
                    No appointments fetched from connected Google Calendar service.
                  </Text>
                </View>
              ) : (
                <View style={styles.scheduleGrid}>
                  {calendarEvents.map((evt, idx) => (
                    <View key={idx} style={styles.appointmentPodOuter}>
                      <View style={styles.appointmentPodInner}>
                        <View style={styles.appointmentTimeCol}>
                          <Text style={styles.appointmentTimeText}>
                            {evt.time || evt.start || "Today"}
                          </Text>
                          <View style={styles.appointmentVerifiedDot} />
                        </View>
                        <View style={styles.appointmentBodyCol}>
                          <Text style={styles.appointmentTitleText}>
                            {evt.summary || evt.title}
                          </Text>
                          {evt.location && (
                            <Text style={styles.appointmentLocationText}>
                              {evt.location}
                            </Text>
                          )}
                        </View>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </View>
          </View>
        </View>
      )}

      <View style={{ height: 120 }} />

      {/* ── Section 5: Aerospace New Deliverable Modal ── */}
      <Modal
        visible={isModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setIsModalOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalOuterBezel}>
            <View style={styles.modalInnerCore}>
              <View style={styles.modalHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.modalTitle}>COMMIT NEW DELIVERABLE</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setIsModalOpen(false)}
                  style={styles.modalCloseX}
                >
                  <Text style={styles.modalCloseXText}>✕</Text>
                </TouchableOpacity>
              </View>

              {/* Priority Selector */}
              <Text style={styles.inputFieldLabel}>PRIORITY LEVEL</Text>
              <View style={styles.prioSelectorRow}>
                {(["normal", "high", "urgent"] as const).map((p) => {
                  const active = newPriority === p;
                  return (
                    <TouchableOpacity
                      key={p}
                      style={[styles.prioSelectorBtn, active && styles.prioSelectorBtnActive]}
                      onPress={() => setNewPriority(p)}
                      activeOpacity={0.8}
                    >
                      <Text
                        style={[
                          styles.prioSelectorText,
                          active && styles.prioSelectorTextActive,
                        ]}
                      >
                        {p.toUpperCase()}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={styles.inputFieldLabel}>DELIVERABLE TITLE</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={newTitle}
                onChangeText={setNewTitle}
                placeholder="e.g. Complete architecture review"
                placeholderTextColor="#8E887E"
                autoCapitalize="sentences"
              />

              <Text style={styles.inputFieldLabel}>TARGET DEADLINE (OPTIONAL)</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={newDeadline}
                onChangeText={setNewDeadline}
                placeholder="e.g. 18:00, Tomorrow, or Friday"
                placeholderTextColor="#8E887E"
              />

              <View style={styles.modalActionsRow}>
                <TouchableOpacity
                  style={styles.cancelActionBtn}
                  onPress={() => setIsModalOpen(false)}
                >
                  <Text style={styles.cancelActionText}>CANCEL</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.commitActionBtn}
                  onPress={handleCreateTask}
                >
                  <Text style={styles.commitActionText}>COMMIT DELIVERABLE</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  contentContainer: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 40,
  },

  // ── Header Outer Bezel & Inner Core (Cockpit Style) ──
  headerOuterBezel: {
    backgroundColor: "#141414",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 3,
    marginBottom: 12,
  },
  headerInnerCore: {
    backgroundColor: "#1A1A1A",
    borderRadius: 17,
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  greetingBlock: {
    flex: 1,
    marginRight: 10,
  },
  systemTagRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 4,
    gap: 6,
  },
  pulseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  pulseDotOffline: {
    backgroundColor: theme.colors.amber,
  },
  systemTagText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  systemSeparator: {
    color: theme.colors.textGhost,
    fontSize: 8,
  },
  systemNodeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  greetingTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 18,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    letterSpacing: -0.3,
  },
  greetingSub: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textSecondary,
    marginTop: 2,
    lineHeight: 15,
  },

  // Aerospace Precision Capsule
  chronoCapsule: {
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 10,
    paddingVertical: 7,
    alignItems: "flex-end",
    flexShrink: 0,
  },
  chronoTopRow: {
    flexDirection: "row",
    alignItems: "baseline",
  },
  chronoDigits: {
    fontFamily: theme.fonts.mono,
    fontSize: 12.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },
  chronoDate: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 0.6,
    marginTop: 2,
  },

  // ── Directives Capsule Bar ──
  directiveOuterBezel: {
    backgroundColor: "#141414",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 3,
    marginBottom: 12,
  },
  directiveInnerCore: {
    backgroundColor: "#1A1A1A",
    borderRadius: 15,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  directiveInputRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#121212",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginBottom: 8,
    overflow: "hidden",
  },
  directivePrefix: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.amber,
    marginRight: 6,
    fontWeight: "700",
    flexShrink: 0,
  },
  directiveInput: {
    flex: 1,
    minWidth: 0,
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.sans,
    fontSize: 11.5,
    paddingVertical: 4,
    paddingHorizontal: 2,
  },
  directiveRunBtn: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
    flexShrink: 0,
  },
  directiveRunBtnDisabled: {
    opacity: 0.4,
  },
  directiveRunText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  directiveRunTextDisabled: {
    color: theme.colors.textMuted,
  },
  chipsRow: {
    flexDirection: "row",
    gap: 6,
    flexWrap: "wrap",
  },
  chipPill: {
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  chipPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
    fontWeight: "600",
  },

  // ── Segmented Aerospace Subtabs Switcher ──
  subTabsOuter: {
    backgroundColor: "#141414",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 3,
    marginBottom: 12,
  },
  subTabsScrollContent: {
    flexDirection: "row",
    backgroundColor: "#1A1A1A",
    borderRadius: 11,
    padding: 2,
    gap: 4,
    alignItems: "center",
  },
  subTabPill: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
  },
  subTabPillActive: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  subTabPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.6,
    fontWeight: "600",
  },
  subTabPillTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },

  // Search Filter Wrap
  searchBarWrap: {
    marginBottom: 12,
  },
  aerospaceSearchInput: {
    backgroundColor: "#141414",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.sans,
    fontSize: 11.5,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },

  // ── Bento Cards: Hero Deck ──
  tabContentCol: {
    gap: 12,
  },
  heroOuterBezel: {
    backgroundColor: "#141414",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 3,
  },
  heroInnerCore: {
    backgroundColor: "#1A1A1A",
    borderRadius: 17,
    padding: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  bentoHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  bentoTagWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flexShrink: 1,
  },
  bentoAmberDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.amber,
  },
  bentoEmeraldDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  bentoEyebrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
    fontWeight: "700",
    flexShrink: 1,
  },
  bentoLinkCapsule: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    flexShrink: 0,
  },
  bentoLinkText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
    fontWeight: "600",
  },

  // Tactical Horizon Focus Pod
  topTaskCard: {
    backgroundColor: "#121212",
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    marginBottom: 12,
  },
  topTaskHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  topTaskBadgeWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    flexShrink: 1,
  },
  priorityDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  topTaskPriorityText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
    fontWeight: "700",
    flexShrink: 1,
  },
  topTaskDeadlineBadge: {
    backgroundColor: "rgba(245, 158, 11, 0.1)",
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.25)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    flexShrink: 0,
  },
  topTaskDeadlineText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.amber,
    fontWeight: "700",
  },
  topTaskTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    lineHeight: 19,
    marginBottom: 10,
  },
  topTaskActionRow: {
    flexDirection: "row",
    gap: 8,
  },
  topTaskCompleteBtn: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.35)",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  topTaskCompleteText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  topTaskDetailsBtn: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  topTaskDetailsText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textSecondary,
    fontWeight: "600",
    letterSpacing: 0.5,
  },
  emptyTopTaskBox: {
    backgroundColor: "#121212",
    borderRadius: 14,
    padding: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    marginBottom: 12,
    gap: 4,
  },
  emptyTopTaskTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  emptyTopTaskSub: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    textAlign: "center",
  },

  // Gauges - Fixed to prevent any label wrapping or clipping
  gaugesContainerRow: {
    flexDirection: "row",
    gap: 8,
  },
  gaugeBox: {
    flex: 1,
    backgroundColor: "#121212",
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    overflow: "hidden",
  },
  gaugeHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
    gap: 4,
  },
  gaugeLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 0.6,
    fontWeight: "700",
    flexShrink: 1,
  },
  gaugeAmount: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    flexShrink: 0,
  },
  gaugeTrack: {
    height: 4,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderRadius: 2,
    overflow: "hidden",
  },
  gaugeFill: {
    height: "100%",
    borderRadius: 2,
  },
  gaugeFillEmerald: {
    backgroundColor: theme.colors.emerald,
  },
  gaugeFillAmber: {
    backgroundColor: theme.colors.amber,
  },
  gaugeSubText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7.5,
    color: theme.colors.textMuted,
    marginTop: 5,
    letterSpacing: 0.3,
  },

  // Appointments Schedule Grid
  scheduleGrid: {
    gap: 8,
  },
  appointmentPodOuter: {
    backgroundColor: "#121212",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2,
  },
  appointmentPodInner: {
    backgroundColor: "#161616",
    borderRadius: 10,
    padding: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  appointmentTimeCol: {
    alignItems: "center",
    minWidth: 60,
    borderRightWidth: 1,
    borderRightColor: "rgba(255, 255, 255, 0.06)",
    paddingRight: 8,
  },
  appointmentTimeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.amber,
    fontWeight: "700",
  },
  appointmentVerifiedDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: theme.colors.emerald,
    marginTop: 4,
  },
  appointmentBodyCol: {
    flex: 1,
  },
  appointmentTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    lineHeight: 16,
  },
  appointmentLocationText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    marginTop: 2,
  },

  // Deliverables Stream Pods
  taskPodOuter: {
    backgroundColor: "#141414",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2.5,
    marginBottom: 8,
  },
  taskPodInner: {
    backgroundColor: "#1A1A1A",
    borderRadius: 12,
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  taskCheckbox: {
    width: 22,
    height: 22,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: "rgba(255, 255, 255, 0.25)",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    alignItems: "center",
    justifyContent: "center",
  },
  taskCheckboxDone: {
    backgroundColor: theme.colors.emerald,
    borderColor: theme.colors.emerald,
  },
  taskCheckGlyph: {
    color: "#000000",
    fontSize: 12,
    fontWeight: "bold",
  },
  taskBodyCol: {
    flex: 1,
  },
  taskTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    color: theme.colors.boneWhite,
    fontWeight: "500",
    lineHeight: 18,
  },
  taskTitleTextDone: {
    color: theme.colors.textMuted,
    textDecorationLine: "line-through",
  },
  taskMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 4,
    flexWrap: "wrap",
  },
  urgentBadge: {
    backgroundColor: "rgba(239, 68, 68, 0.15)",
    borderWidth: 1,
    borderColor: "rgba(239, 68, 68, 0.4)",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  urgentBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7.5,
    color: theme.colors.crimson,
    fontWeight: "700",
  },
  highBadge: {
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.4)",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  highBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7.5,
    color: theme.colors.amber,
    fontWeight: "700",
  },
  taskDeadlineText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textSecondary,
  },
  taskAgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
  },
  taskDeleteBtn: {
    padding: 6,
    opacity: 0.6,
  },
  taskDeleteGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
  },

  // Stream Headers & Empty States
  streamHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 4,
    marginBottom: 4,
  },
  streamHeaderTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  emptyOuterBezel: {
    backgroundColor: "#141414",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 3,
  },
  emptyInnerCore: {
    backgroundColor: "#1A1A1A",
    borderRadius: 13,
    padding: 24,
    alignItems: "center",
    gap: 6,
  },
  emptyTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 13.5,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  emptySubtitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    textAlign: "center",
    lineHeight: 14,
  },
  emptyTasksPod: {
    backgroundColor: "#121212",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
    gap: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
  },
  emptyTasksTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  emptyTasksSub: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    textAlign: "center",
  },

  // ── Modal Styles ──
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.8)",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  modalOuterBezel: {
    width: "100%",
    backgroundColor: "#141414",
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
    padding: 3,
  },
  modalInnerCore: {
    backgroundColor: "#1A1A1A",
    borderRadius: 19,
    padding: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
  },
  modalHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
  },
  modalTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  modalCloseX: {
    padding: 4,
  },
  modalCloseXText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
  },
  inputFieldLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.7,
    fontWeight: "700",
    marginBottom: 6,
    marginTop: 10,
  },
  prioSelectorRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 6,
  },
  prioSelectorBtn: {
    flex: 1,
    paddingVertical: 7,
    alignItems: "center",
    borderRadius: 8,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  prioSelectorBtnActive: {
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    borderColor: theme.colors.amber,
  },
  prioSelectorText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    fontWeight: "600",
  },
  prioSelectorTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  aerospaceInput: {
    backgroundColor: "#121212",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  modalActionsRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 10,
    marginTop: 20,
  },
  cancelActionBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  cancelActionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    fontWeight: "600",
  },
  commitActionBtn: {
    backgroundColor: theme.colors.boneWhite,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  commitActionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#000000",
    fontWeight: "700",
    letterSpacing: 0.5,
  },
});
