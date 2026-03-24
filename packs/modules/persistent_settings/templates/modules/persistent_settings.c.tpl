#include "persistent_settings.h"

#include <string.h>

static uint8_t PersistentSettings_TimeReached(uint32_t now_ms, uint32_t timestamp_ms)
{
    return ((int32_t)(now_ms - timestamp_ms) >= 0) ? 1U : 0U;
}

void PersistentSettings_Init(
    PersistentSettings *settings,
    const char *name,
    uint8_t *data,
    uint16_t length,
    uint16_t version,
    uint32_t commit_delay_ms
)
{
    if (settings == NULL) {
        return;
    }

    settings->name = name;
    settings->data = data;
    settings->length = length;
    settings->version = version;
    settings->loaded = 0U;
    settings->dirty = 0U;
    settings->commit_delay_ms = commit_delay_ms;
    settings->dirty_since_ms = 0U;
    settings->last_commit_ms = 0U;

    if (settings->data != NULL && settings->length > 0U) {
        memset(settings->data, 0, settings->length);
    }
}

void PersistentSettings_Load(PersistentSettings *settings)
{
    HAL_StatusTypeDef status;

    if (settings == NULL || settings->data == NULL || settings->length == 0U) {
        return;
    }

    PersistentSettings_OnDefaults(settings, settings->data, settings->length);
    status = PersistentSettings_OnLoad(settings, settings->data, settings->length, settings->version);
    settings->loaded = (status == HAL_OK) ? 1U : 0U;
    settings->dirty = 0U;
    settings->dirty_since_ms = 0U;
    PersistentSettings_OnStatus(settings, status, 1U);
}

void PersistentSettings_RequestDefaults(PersistentSettings *settings)
{
    if (settings == NULL || settings->data == NULL || settings->length == 0U) {
        return;
    }

    PersistentSettings_OnDefaults(settings, settings->data, settings->length);
    settings->loaded = 1U;
    PersistentSettings_MarkDirty(settings);
}

void PersistentSettings_RequestCommit(PersistentSettings *settings)
{
    HAL_StatusTypeDef status;

    if (settings == NULL || settings->data == NULL || settings->length == 0U) {
        return;
    }

    status = PersistentSettings_OnSave(settings, settings->data, settings->length, settings->version);
    if (status == HAL_OK) {
        settings->dirty = 0U;
        settings->dirty_since_ms = 0U;
        settings->last_commit_ms = HAL_GetTick();
    }
    PersistentSettings_OnStatus(settings, status, 0U);
}

void PersistentSettings_MarkDirty(PersistentSettings *settings)
{
    if (settings == NULL) {
        return;
    }

    settings->dirty = 1U;
    if (settings->dirty_since_ms == 0U) {
        settings->dirty_since_ms = HAL_GetTick();
    }
}

void PersistentSettings_Process(PersistentSettings *settings, uint32_t now_ms)
{
    if (settings == NULL || settings->dirty == 0U) {
        return;
    }

    if (settings->commit_delay_ms == 0U
        || PersistentSettings_TimeReached(now_ms, settings->dirty_since_ms + settings->commit_delay_ms)) {
        PersistentSettings_RequestCommit(settings);
    }
}

void PersistentSettings_TaskCallback(void *user_data)
{
    PersistentSettings *settings = (PersistentSettings *)user_data;
    PersistentSettings_Process(settings, HAL_GetTick());
}

uint8_t *PersistentSettings_Data(PersistentSettings *settings)
{
    if (settings == NULL) {
        return NULL;
    }
    return settings->data;
}

const uint8_t *PersistentSettings_ConstData(const PersistentSettings *settings)
{
    if (settings == NULL) {
        return NULL;
    }
    return settings->data;
}

uint8_t PersistentSettings_IsLoaded(const PersistentSettings *settings)
{
    if (settings == NULL) {
        return 0U;
    }
    return settings->loaded;
}

uint8_t PersistentSettings_Matches(const PersistentSettings *settings, const char *name)
{
    if (settings == NULL || settings->name == NULL || name == NULL) {
        return 0U;
    }
    return (strcmp(settings->name, name) == 0) ? 1U : 0U;
}

__weak void PersistentSettings_OnDefaults(PersistentSettings *settings, uint8_t *data, uint16_t length)
{
    (void)settings;
    if (data != NULL && length > 0U) {
        memset(data, 0, length);
    }
}

__weak HAL_StatusTypeDef PersistentSettings_OnLoad(PersistentSettings *settings, uint8_t *data, uint16_t length, uint16_t version)
{
    (void)settings;
    (void)data;
    (void)length;
    (void)version;
    return HAL_ERROR;
}

__weak HAL_StatusTypeDef PersistentSettings_OnSave(const PersistentSettings *settings, const uint8_t *data, uint16_t length, uint16_t version)
{
    (void)settings;
    (void)data;
    (void)length;
    (void)version;
    return HAL_ERROR;
}

__weak void PersistentSettings_OnStatus(PersistentSettings *settings, HAL_StatusTypeDef status, uint8_t is_load)
{
    (void)settings;
    (void)status;
    (void)is_load;
}
