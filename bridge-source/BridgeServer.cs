using System;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Text.Json;
using System.Collections.Concurrent;
using System.Collections.Generic;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

namespace RevitAgentBridge
{
    public static class BridgeRegistry
    {
        public static BridgeServer ActiveServer { get; set; }
        public static ExternalEvent ActiveEvent { get; set; }
    }

    public class AgentTask
    {
        public string RequestJson { get; }
        public string ResultJson { get; set; }
        public AutoResetEvent CompletionEvent { get; }

        public AgentTask(string json)
        {
            RequestJson = json ?? "{}";
            ResultJson = "{}";
            CompletionEvent = new AutoResetEvent(false);
        }
    }

    public class AgentExternalEventHandler : IExternalEventHandler
    {
        private readonly ConcurrentQueue<AgentTask> _taskQueue = new ConcurrentQueue<AgentTask>();

        public void EnqueueTask(AgentTask task)
        {
            if (task != null)
            {
                _taskQueue.Enqueue(task);
            }
        }

        public void Execute(UIApplication app)
        {
            if (app?.ActiveUIDocument == null) return;

            Document doc = app.ActiveUIDocument.Document;

            while (_taskQueue.TryDequeue(out AgentTask task))
            {
                try
                {
                    using (JsonDocument document = JsonDocument.Parse(task.RequestJson))
                    {
                        JsonElement root = document.RootElement;
                        string action = root.GetProperty("action").GetString();

                        // ACTION 1: Get Active Document Context (Dynamic Levels & Families)
                        if (action == "get_context")
                        {
                            var levelsList = new List<object>();
                            var familiesDict = new Dictionary<string, List<string>>();

                            // Collect Levels
                            var levelCollector = new FilteredElementCollector(doc).OfClass(typeof(Level));
                            foreach (Level lvl in levelCollector)
                            {
                                levelsList.Add(new
                                {
                                    name = lvl.Name,
                                    id = lvl.UniqueId,
                                    elevation = lvl.Elevation // in decimal feet
                                });
                            }

                            // Collect Loaded Family Symbols
                            var symbolCollector = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol));
                            foreach (FamilySymbol symbol in symbolCollector)
                            {
                                string famName = symbol.Family.Name;
                                string typeName = symbol.Name;

                                if (!familiesDict.ContainsKey(famName))
                                {
                                    familiesDict[famName] = new List<string>();
                                }
                                if (!familiesDict[famName].Contains(typeName))
                                {
                                    familiesDict[famName].Add(typeName);
                                }
                            }

                            var contextObj = new
                            {
                                status = "success",
                                document_title = doc.Title,
                                levels = levelsList,
                                families = familiesDict
                            };

                            task.ResultJson = JsonSerializer.Serialize(contextObj);
                        }
                        // ACTION 2: Real physical Family Placement inside Transaction
                        else if (action == "place_family")
                        {
                            JsonElement parameters = root.GetProperty("parameters");
                            string familyName = parameters.GetProperty("family_name").GetString();
                            string typeName = parameters.GetProperty("type_name").GetString();
                            string levelId = parameters.GetProperty("level_id").GetString();

                            JsonElement coordinates = parameters.GetProperty("coordinates");
                            double x = coordinates.GetProperty("x").GetDouble();
                            double y = coordinates.GetProperty("y").GetDouble();
                            double z = coordinates.GetProperty("z").GetDouble();

                            // 1. Resolve Target Level
                            Element levelElement = doc.GetElement(levelId);
                            Level level = levelElement as Level;
                            if (level == null)
                            {
                                throw new ArgumentException($"The level ID '{levelId}' is invalid or does not exist.");
                            }

                            // 2. Resolve Target Family Symbol
                            FamilySymbol targetSymbol = null;
                            var symbolCollector = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol));
                            foreach (FamilySymbol s in symbolCollector)
                            {
                                if (s.Family.Name.Equals(familyName, StringComparison.OrdinalIgnoreCase) &&
                                    s.Name.Equals(typeName, StringComparison.OrdinalIgnoreCase))
                                {
                                    targetSymbol = s;
                                    break;
                                }
                            }

                            if (targetSymbol == null)
                            {
                                throw new InvalidOperationException($"The family symbol '{familyName}' with type '{typeName}' is not loaded in this project.");
                            }

                            string placedElementId = string.Empty;

                            // 3. Open a Revit Transaction and execute placement
                            using (Transaction trans = new Transaction(doc, "AI Agent - Place Family"))
                            {
                                trans.Start();

                                // Symbol must be activated before placement to prevent crash
                                if (!targetSymbol.IsActive)
                                {
                                    targetSymbol.Activate();
                                    doc.Regenerate();
                                }

                                XYZ insertionPoint = new XYZ(x, y, z);
                                
                                FamilyInstance instance = doc.Create.NewFamilyInstance(
                                    insertionPoint,
                                    targetSymbol,
                                    level,
                                    Autodesk.Revit.DB.Structure.StructuralType.NonStructural
                                );

                                trans.Commit();
                                placedElementId = instance.UniqueId;
                            }

                            var placementResponse = new
                            {
                                status = "success",
                                message = "Successfully placed element in Revit model.",
                                element_id = placedElementId
                            };

                            task.ResultJson = JsonSerializer.Serialize(placementResponse);
                        }
                        else
                        {
                            var errorObj = new { status = "error", message = $"Action '{action}' is not supported." };
                            task.ResultJson = JsonSerializer.Serialize(errorObj);
                        }
                    }
                }
                catch (Exception ex)
                {
                    var exceptionObj = new { status = "error", message = $"Placement error inside Revit: {ex.Message}" };
                    task.ResultJson = JsonSerializer.Serialize(exceptionObj);
                }
                finally
                {
                    task.CompletionEvent.Set();
                }
            }
        }

        public string GetName()
        {
            return "BIM Agent External Event Handler";
        }
    }

    public class BridgeServer
    {
        private HttpListener _listener;
        private Thread _listenerThread;
        private readonly AgentExternalEventHandler _handler;
        private readonly ExternalEvent _externalEvent;
        private bool _isRunning;

        public BridgeServer(AgentExternalEventHandler handler, ExternalEvent externalEvent)
        {
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            _externalEvent = externalEvent ?? throw new ArgumentNullException(nameof(externalEvent));
        }

        public void Start(int port)
        {
            if (_isRunning) return;

            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/execute/");
            _listener.Start();
            _isRunning = true;

            _listenerThread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name = "RevitAgentBridge_HTTP_Listener"
            };
            _listenerThread.Start();
        }

        private void ListenLoop()
        {
            while (_isRunning && _listener != null && _listener.IsListening)
            {
                try
                {
                    HttpListenerContext context = _listener.GetContext();
                    HttpListenerRequest request = context.Request;

                    string jsonPayload;
                    using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                    {
                        jsonPayload = reader.ReadToEnd();
                    }

                    var task = new AgentTask(jsonPayload);
                    _handler.EnqueueTask(task);
                    _externalEvent.Raise();

                    task.CompletionEvent.WaitOne();

                    byte[] buffer = Encoding.UTF8.GetBytes(task.ResultJson);
                    context.Response.ContentType = "application/json";
                    context.Response.ContentLength64 = buffer.Length;
                    context.Response.OutputStream.Write(buffer, 0, buffer.Length);
                    context.Response.OutputStream.Close();
                }
                catch (HttpListenerException)
                {
                    break;
                }
                catch (Exception)
                {
                    // Safeguard execution thread
                }
            }
        }

        public void Stop()
        {
            _isRunning = false;
            if (_listener != null)
            {
                try
                {
                    _listener.Stop();
                    _listener.Close();
                }
                catch { }
                _listener = null;
            }

            if (_listenerThread != null && _listenerThread.IsAlive)
            {
                _listenerThread.Join(1000);
                _listenerThread = null;
            }
        }
    }
}