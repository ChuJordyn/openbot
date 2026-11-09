#import <Cocoa/Cocoa.h>

static NSString *supportDirectory(void) {
    NSString *override = NSProcessInfo.processInfo.environment[@"OPENBOT_CUSTOM_SUPPORT_DIR"];
    if (override.length && override.isAbsolutePath) return override;
    return [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/OpenBot Custom"];
}

static NSError *failure(NSString *message) {
    return [NSError errorWithDomain:@"OpenBotStandalone" code:1
                          userInfo:@{NSLocalizedDescriptionKey:message}];
}

static BOOL runTool(NSString *executable, NSArray<NSString *> *arguments, NSError **error) {
    NSTask *task = [NSTask new];
    task.executableURL = [NSURL fileURLWithPath:executable];
    task.arguments = arguments;
    NSPipe *output = [NSPipe pipe];
    task.standardOutput = output;
    task.standardError = output;
    if (![task launchAndReturnError:error]) return NO;
    NSData *data = [output.fileHandleForReading readDataToEndOfFile];
    [task waitUntilExit];
    if (task.terminationStatus != 0) {
        NSString *detail = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        *error = failure(detail.length ? detail : @"无法准备完整程序。");
        return NO;
    }
    return YES;
}

static BOOL validApplication(NSString *path) {
    NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:
        [path stringByAppendingPathComponent:@"Contents/Info.plist"]];
    NSString *binary = info[@"CFBundleExecutable"];
    return [info[@"CFBundleIdentifier"] isEqualToString:@"app.openbot.desktop"] && binary.length &&
        [NSFileManager.defaultManager isExecutableFileAtPath:
            [[path stringByAppendingPathComponent:@"Contents/MacOS"] stringByAppendingPathComponent:binary]] &&
        [NSFileManager.defaultManager fileExistsAtPath:
            [path stringByAppendingPathComponent:@"Contents/Resources/app.asar"]];
}

static NSURL *prepareApplication(NSError **error) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *parent = [supportDirectory() stringByAppendingPathComponent:@"Application"];
    NSString *target = [parent stringByAppendingPathComponent:@"OpenBot.app"];
    if ([fm fileExistsAtPath:target]) {
        if (validApplication(target)) return [NSURL fileURLWithPath:target];
        *error = failure(@"已安装的运行组件不完整，请保留现有数据并重新安装完整版。");
        return nil;
    }
    NSString *archive = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"OpenBot-runtime.zip"];
    if (![fm fileExistsAtPath:archive]) {
        *error = failure(@"App 内缺少完整程序，请重新获取完整版。");
        return nil;
    }
    if (![fm createDirectoryAtPath:parent withIntermediateDirectories:YES
                        attributes:@{NSFilePosixPermissions:@0700} error:error]) return nil;
    NSString *staging = [parent stringByAppendingPathComponent:
        [@"install-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    if (![fm createDirectoryAtPath:staging withIntermediateDirectories:NO
                        attributes:@{NSFilePosixPermissions:@0700} error:error]) return nil;
    NSString *unpacked = [staging stringByAppendingPathComponent:@"OpenBot.app"];
    BOOL ok = runTool(@"/usr/bin/ditto", @[@"-x", @"-k", archive, staging], error);
    if (ok && !validApplication(unpacked)) {
        *error = failure(@"内置程序解包检查失败。");
        ok = NO;
    }
    // The official application remains unmodified and keeps its original signature.
    if (ok) ok = runTool(@"/usr/bin/codesign", @[@"--verify", @"--deep", @"--strict", unpacked], error);
    if (ok) ok = [fm moveItemAtPath:unpacked toPath:target error:error];
    [fm removeItemAtPath:staging error:nil];
    return ok ? [NSURL fileURLWithPath:target] : nil;
}

static BOOL prepareConfiguration(NSString **runtimePath, NSError **error) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *source = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"openbot-main-config"];
    NSString *support = [supportDirectory() stringByAppendingPathComponent:@"runtime"];
    if (![fm createDirectoryAtPath:support withIntermediateDirectories:YES
                        attributes:@{NSFilePosixPermissions:@0700} error:error]) return NO;
    for (NSString *name in @[@"grok-main", @"coordinator.md", @"main-grok.toml", @"acp_bridge.py", @"bridge_policy.py"]) {
        NSData *data = [NSData dataWithContentsOfFile:[source stringByAppendingPathComponent:name] options:0 error:error];
        if (!data) return NO;
        NSString *destination = [support stringByAppendingPathComponent:name];
        if (![data isEqualToData:[NSData dataWithContentsOfFile:destination]] &&
            ![data writeToFile:destination options:NSDataWritingAtomic error:error]) return NO;
        NSNumber *mode = [name isEqualToString:@"grok-main"] ? @0700 : @0600;
        if (![fm setAttributes:@{NSFilePosixPermissions:mode} ofItemAtPath:destination error:error]) return NO;
    }
    *runtimePath = support;
    return YES;
}

static void showError(NSString *message) {
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"暂时无法打开 OpenBot Custom";
    alert.informativeText = message;
    [alert runModal];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        BOOL check = argc == 2 && strcmp(argv[1], "--check") == 0;
        NSError *error = nil;
        NSString *runtime = nil;
        NSURL *target = prepareApplication(&error);
        BOOL ready = target && prepareConfiguration(&runtime, &error);
        if (!ready) {
            if (check) { fprintf(stderr, "%s\n", error.localizedDescription.UTF8String); return 1; }
            [NSApplication sharedApplication];
            showError(error.localizedDescription ?: @"启动配置尚未准备好。");
            return 1;
        }
        NSString *settingsPath = [[runtime stringByDeletingLastPathComponent]
            stringByAppendingPathComponent:@"settings.json"];
        NSData *settingsData = [NSData dataWithContentsOfFile:settingsPath];
        NSDictionary *settings = @{};
        if (settingsData) {
            id parsed = [NSJSONSerialization JSONObjectWithData:settingsData options:0 error:&error];
            if (![parsed isKindOfClass:NSDictionary.class]) {
                if (check) { fprintf(stderr, "Invalid settings.json\n"); return 1; }
                [NSApplication sharedApplication];
                showError(@"settings.json 格式不正确，请按示例填写。");
                return 1;
            }
            settings = parsed;
        }
        NSMutableDictionary *environment = [NSMutableDictionary dictionary];
        for (NSString *key in @[@"HTTP_PROXY", @"HTTPS_PROXY", @"ALL_PROXY", @"NO_PROXY"]) {
            NSString *value = NSProcessInfo.processInfo.environment[key];
            if (value.length) environment[key] = value;
        }
        NSDictionary *mapping = @{@"httpProxy":@"HTTP_PROXY", @"httpsProxy":@"HTTPS_PROXY",
            @"codexPath":@"OPENBOT_CODEX_PATH", @"grokPath":@"OPENBOT_REAL_GROK_PATH"};
        for (NSString *key in mapping) {
            id value = settings[key];
            if ([value isKindOfClass:NSString.class] && [value length]) environment[mapping[key]] = value;
        }
        environment[@"OPENBOT_GROK_PATH"] = [runtime stringByAppendingPathComponent:@"grok-main"];
        NSArray<NSRunningApplication *> *running =
            [NSRunningApplication runningApplicationsWithBundleIdentifier:@"app.openbot.desktop"];
        if (check) {
            NSMutableArray *paths = [NSMutableArray array];
            for (NSRunningApplication *app in running) if (app.bundleURL.path) [paths addObject:app.bundleURL.path];
            NSData *json = [NSJSONSerialization dataWithJSONObject:
                @{@"ready":@YES, @"selfContained":@YES, @"application":target.path,
                  @"runtime":runtime, @"environmentKeys":environment.allKeys, @"runningApplications":paths}
                options:NSJSONWritingPrettyPrinted error:&error];
            if (!json) return 1;
            fwrite(json.bytes, 1, json.length, stdout); fputc('\n', stdout);
            return 0;
        }
        [NSApplication sharedApplication];
        for (NSRunningApplication *app in running) {
            if (![app.bundleURL.URLByResolvingSymlinksInPath.path isEqualToString:target.URLByResolvingSymlinksInPath.path]) {
                showError(@"请先用 ⌘Q 退出当前旧版 OpenBot，再打开完整版。这样才能切换到完整程序；不要删除聊天数据或项目文件。");
                return 1;
            }
        }
        NSWorkspaceOpenConfiguration *configuration = [NSWorkspaceOpenConfiguration configuration];
        configuration.environment = environment;
        configuration.activates = YES;
        [NSWorkspace.sharedWorkspace openApplicationAtURL:target configuration:configuration
            completionHandler:^(NSRunningApplication *app, NSError *launchError) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (launchError) {
                        showError(launchError.localizedDescription);
                    } else if (![app.bundleURL.URLByResolvingSymlinksInPath.path isEqualToString:target.URLByResolvingSymlinksInPath.path]) {
                        showError(@"Mac 仍打开了另一份 OpenBot。请退出旧版后再次打开完整版。");
                    }
                    [NSApp terminate:nil];
                });
            }];
        [NSApp run];
    }
    return 0;
}
