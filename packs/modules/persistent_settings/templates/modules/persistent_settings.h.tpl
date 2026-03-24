#ifndef __PERSISTENT_SETTINGS_H
#define __PERSISTENT_SETTINGS_H

#include "main.h"

typedef struct
{
    const char *name;
    uint8_t *data;
    uint16_t length;
    uint16_t version;
    uint8_t loaded;
    uint8_t dirty;
    uint32_t commit_delay_ms;
    uint32_t dirty_since_ms;
    uint32_t last_commit_ms;
} PersistentSettings;

void PersistentSettings_Init(
    PersistentSettings *settings,
    const char *name,
    uint8_t *data,
    uint16_t length,
    uint16_t version,
    uint32_t commit_delay_ms
);
void PersistentSettings_Load(PersistentSettings *settings);
void PersistentSettings_RequestDefaults(PersistentSettings *settings);
void PersistentSettings_RequestCommit(PersistentSettings *settings);
void PersistentSettings_MarkDirty(PersistentSettings *settings);
void PersistentSettings_Process(PersistentSettings *settings, uint32_t now_ms);
void PersistentSettings_TaskCallback(void *user_data);
uint8_t *PersistentSettings_Data(PersistentSettings *settings);
const uint8_t *PersistentSettings_ConstData(const PersistentSettings *settings);
uint8_t PersistentSettings_IsLoaded(const PersistentSettings *settings);
uint8_t PersistentSettings_Matches(const PersistentSettings *settings, const char *name);

void PersistentSettings_OnDefaults(PersistentSettings *settings, uint8_t *data, uint16_t length);
HAL_StatusTypeDef PersistentSettings_OnLoad(PersistentSettings *settings, uint8_t *data, uint16_t length, uint16_t version);
HAL_StatusTypeDef PersistentSettings_OnSave(const PersistentSettings *settings, const uint8_t *data, uint16_t length, uint16_t version);
void PersistentSettings_OnStatus(PersistentSettings *settings, HAL_StatusTypeDef status, uint8_t is_load);

#endif
